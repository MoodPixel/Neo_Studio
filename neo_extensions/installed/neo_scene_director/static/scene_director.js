(function () {
  const EXTENSION_ID = 'image.scene_director';
  const ALLOWED_FAMILIES = new Set(['sdxl_sd', 'sdxl', 'sd', 'sd15', 'sd1.5']);
  const BLOCKED_FAMILIES = new Set(['flux', 'qwen', 'qwen_image_edit', 'zimage']);
  const STATE_KEY = 'neo_scene_director_ui_state_v1';
  const DEFAULT_CONTRACTS = {
    enabled: true,
    use_node_auto_prompts: false,
    count_contract: 'exactly {count} visible subjects, one subject per enabled region, no extra subjects',
    subject_contract: 'one complete subject inside this region, not merged, not duplicated',
    negative_contract: 'extra people, missing subject, wrong number of subjects, merged bodies, fused faces',
    style_merge: 'use Neo main prompt as the scene style and composition intent'
  };


  function ensureCanonicalImageState(callback) {
    if (window.NeoImageState) {
      callback && callback();
      return;
    }
    if (window.__neoImageStateScriptLoading) {
      window.addEventListener('neo-image-state-changed', () => callback && callback(), { once: true });
      window.setTimeout(() => callback && callback(), 800);
      return;
    }
    window.__neoImageStateScriptLoading = true;
    const script = document.createElement('script');
    script.src = '/static/js/image_state.js';
    script.async = false;
    script.onload = () => { callback && callback(); };
    script.onerror = () => { callback && callback(); };
    document.head.appendChild(script);
  }

  const MIN_RECT_SIZE = 0.035;
  let selectedRegionId = null;
  let activeInteraction = null;

  let mounted = false;
  let registryRecord = null;
  let regions = [];

  function installGenerationSizeBridge() {
    if (window.__neoSceneDirectorSizeBridgeInstalled) return;
    window.__neoSceneDirectorSizeBridgeInstalled = true;
    const rememberPayload = (body) => {
      try {
        let payload = body;
        if (typeof payload === 'string') payload = JSON.parse(payload);
        if (!payload || typeof payload !== 'object') return;
        if (payload.width || payload.height || payload.size || payload.resolution || payload.generation_size) {
          window.NeoSceneDirectorLastGenerationPayload = payload;
          if (window.NeoImageState?.ingestGenerationPayload) window.NeoImageState.ingestGenerationPayload(payload, 'scene-director-fetch-bridge');
          window.dispatchEvent(new CustomEvent('neo-scene-director-size-changed', { detail: payload }));
        }
      } catch (_) {}
    };
    const originalFetch = window.fetch;
    if (typeof originalFetch === 'function') {
      window.fetch = function(input, init) {
        try {
          const url = String(typeof input === 'string' ? input : input?.url || '');
          if (url.includes('/api/generation') && init?.body) rememberPayload(init.body);
        } catch (_) {}
        return originalFetch.apply(this, arguments);
      };
    }
  }


  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) { return document.getElementById(id); }

  function makeEl(tag, className = '', html = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (html) el.innerHTML = html;
    return el;
  }

  function getFamily() {
    return String($('generation-family')?.value || 'sdxl_sd').trim().toLowerCase();
  }

  function getSize() {
    const DEFAULT_SIZE = { width: 1024, height: 1024 };
    const MIN_SIZE = 64;
    const MAX_SIZE = 8192;
    const shell = () => document.getElementById('neo-scene-director-shell');
    const inSceneDirector = (el) => !!(el && shell() && shell().contains(el));
    const valid = (width, height) => {
      width = parseInt(width, 10);
      height = parseInt(height, 10);
      if (!Number.isFinite(width) || !Number.isFinite(height)) return null;
      if (width < MIN_SIZE || height < MIN_SIZE || width > MAX_SIZE || height > MAX_SIZE) return null;
      return { width, height };
    };
    const parseSizeText = (raw) => {
      const text = String(raw || '').replace(/\s+/g, ' ').trim();
      if (!text) return null;
      const match = text.match(/(?:^|[^0-9])([1-8][0-9]{2,3})\s*[x×]\s*([1-8][0-9]{2,3})(?:[^0-9]|$)/i);
      return match ? valid(match[1], match[2]) : null;
    };
    const isVisible = (el) => {
      if (!el || inSceneDirector(el)) return false;
      if (el.closest?.('[hidden], [aria-hidden="true"], #neo-scene-director-shell')) return false;
      const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
      if (style && (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0)) return false;
      const rect = el.getBoundingClientRect?.();
      return !rect || (rect.width > 0 && rect.height > 0);
    };
    const valueText = (el) => {
      if (!el || inSceneDirector(el)) return '';
      const bits = [];
      if (el.tagName === 'SELECT') {
        bits.push(el.value || '');
        Array.from(el.selectedOptions || []).forEach(opt => bits.push(opt.value || '', opt.textContent || '', opt.dataset?.size || '', opt.dataset?.value || '', opt.getAttribute('data-resolution') || ''));
      } else {
        bits.push(el.value ?? '', el.getAttribute?.('aria-valuenow') || '');
      }
      bits.push(
        el.dataset?.value || '', el.dataset?.size || '', el.dataset?.resolution || '',
        el.dataset?.generationSize || '', el.dataset?.generationResolution || '',
        el.getAttribute?.('data-value') || '', el.getAttribute?.('data-size') || '', el.getAttribute?.('data-resolution') || '',
        el.getAttribute?.('aria-label') || '', el.getAttribute?.('title') || '', el.textContent || ''
      );
      return bits.filter(Boolean).join(' ');
    };
    const contextText = (el) => {
      if (!el || inSceneDirector(el)) return '';
      const bits = [el.id || '', el.name || '', el.className || '', el.getAttribute?.('aria-label') || '', el.getAttribute?.('title') || '', el.placeholder || ''];
      if (el.id && window.CSS?.escape) {
        const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (label) bits.push(label.textContent || '');
      }
      let node = el.closest?.('label, .form-group, .field, .setting-row, .control-row, .generation-field, .input-row, [data-field], [data-setting], [data-section], section, details, fieldset, div');
      for (let i = 0; node && i < 6 && !inSceneDirector(node); i += 1, node = node.parentElement) {
        bits.push(node.id || '', node.className || '', node.getAttribute?.('aria-label') || '', node.getAttribute?.('title') || '', node.dataset?.field || '', node.dataset?.setting || '', node.dataset?.section || '', node.dataset?.tab || '');
        const prev = node.previousElementSibling;
        if (prev && !inSceneDirector(prev)) bits.push(prev.textContent || '', prev.getAttribute?.('aria-label') || '', prev.getAttribute?.('title') || '');
      }
      return bits.join(' ').toLowerCase();
    };
    const numberFrom = (el) => {
      const raw = String(el?.value ?? el?.getAttribute?.('value') ?? el?.getAttribute?.('aria-valuenow') ?? el?.dataset?.value ?? el?.textContent ?? '').trim();
      const n = parseInt(raw.replace(/[^0-9]/g, ''), 10);
      return Number.isFinite(n) && n >= MIN_SIZE && n <= MAX_SIZE ? n : null;
    };

    // HARD LINK: explicit live Build width/height controls first.
    // This runs before saved Scene Director size, cached generation payload, or 1024 fallback.
    const findDimension = (kind) => {
      const selector = [
        `#generation-${kind}`, `#txt2img-${kind}`, `#image-${kind}`, `#neo-${kind}`, `#neo-generation-${kind}`, `#${kind}`,
        `[name="${kind}"]`, `[name="generation_${kind}"]`, `[name="image_${kind}"]`, `[data-generation-${kind}]`, `[data-${kind}]`,
        'input', 'select', '[role="spinbutton"]', '[contenteditable="true"]'
      ].join(',');
      const nodes = Array.from(document.querySelectorAll(selector)).filter(isVisible);
      for (const el of nodes) {
        const ctx = contextText(el);
        if (ctx.includes('scene director') || ctx.includes('regional editor') || ctx.includes('canvas')) continue;
        const idName = String(`${el.id || ''} ${el.name || ''} ${el.getAttribute?.('aria-label') || ''} ${el.placeholder || ''}`).toLowerCase();
        const hasKind = ctx.includes(kind) || idName.includes(kind);
        const looksBuild = ctx.includes('build') || ctx.includes('generation') || ctx.includes('txt2img') || ctx.includes('image') || ctx.includes('size') || ctx.includes('resolution') || ctx.includes('output') || idName.includes(kind);
        if (!hasKind || !looksBuild) continue;
        const n = numberFrom(el);
        if (n) return n;
      }
      return null;
    };
    const explicitWidth = findDimension('width');
    const explicitHeight = findDimension('height');
    const explicitPair = valid(explicitWidth, explicitHeight);
    if (explicitPair) {
      window.NeoImageState?.updateBuild?.({ ...explicitPair, size_source: 'scene-director-linked-build-inputs' }, 'scene-director-linked-build-inputs');
      return explicitPair;
    }

    // Second priority: selected Build size/resolution controls/pills.
    const sizeSelectors = [
      '#generation-size', '#generation-size-preset', '#generation-resolution', '#image-size', '#image-resolution', '#generation-output-size',
      '[name="size"]', '[name="size_preset"]', '[name="resolution"]', '[name="generation_size"]', '[name="image_size"]',
      '[data-generation-size]', '[data-size-preset]', '[data-resolution]', '[data-size]'
    ];
    for (const selector of sizeSelectors) {
      const nodes = Array.from(document.querySelectorAll(selector)).filter(isVisible);
      for (const el of nodes) {
        const parsed = parseSizeText(valueText(el));
        if (parsed) {
          window.NeoImageState?.updateBuild?.({ ...parsed, size_source: 'scene-director-linked-build-size-control' }, 'scene-director-linked-build-size-control');
          return parsed;
        }
      }
    }
    const compactNodes = Array.from(document.querySelectorAll('button, [role="button"], [role="option"], option:checked, select, input, .pill, .chip, .preset, .option, .dropdown, .select, [aria-selected="true"], [aria-pressed="true"], .active, .selected')).filter(isVisible);
    for (const el of compactNodes) {
      const ctx = contextText(el);
      const text = valueText(el);
      if (String(text || '').length > 100) continue;
      if (ctx.includes('scene director') || ctx.includes('regional editor') || ctx.includes('preview shell')) continue;
      const parsed = parseSizeText(text);
      if (!parsed) continue;
      const combined = `${ctx} ${text}`.toLowerCase();
      const looksBuild = combined.includes('build') || combined.includes('generation') || combined.includes('txt2img') || combined.includes('image size') || combined.includes('resolution') || combined.includes('orientation') || combined.includes('aspect') || combined.includes('size');
      if (!looksBuild) continue;
      window.NeoImageState?.updateBuild?.({ ...parsed, size_source: 'scene-director-linked-build-selected-size' }, 'scene-director-linked-build-selected-size');
      return parsed;
    }

    // Then canonical state. Useful after Build bridge captured a value, but never above live controls.
    window.NeoImageState?.refreshBuildSizeFromDom?.('scene-director-get-size');
    const canonicalState = window.NeoImageState?.getState?.();
    const canonicalSize = window.NeoImageState?.getBuildSize?.();
    if (canonicalSize && canonicalSize.width && canonicalSize.height && canonicalState?.build?.size_source !== 'default') return canonicalSize;

    const readFromObject = (obj) => {
      if (!obj || typeof obj !== 'object') return null;
      const direct = valid(obj.width ?? obj.generation_width ?? obj.image_width ?? obj.canvas_width, obj.height ?? obj.generation_height ?? obj.image_height ?? obj.canvas_height);
      if (direct) return direct;
      return parseSizeText(obj.size || obj.resolution || obj.size_preset || obj.generation_size || obj.image_size || obj.output_size);
    };
    const globals = [
      window.NeoSceneDirectorLastGenerationPayload,
      window.NeoStudioCurrentGenerationPayload,
      window.neoStudioCurrentGenerationPayload,
      window.NeoGenerationPayload,
      window.neoGenerationPayload,
      window.NeoStudioApp?.generation?.payload,
      window.NeoStudioApp?.generation?.state,
      window.NeoStudioApp?.generation?.current,
      window.NeoStudioApp?.generation?.draft,
      window.NeoStudioApp?.generation?.formState,
    ];
    for (const obj of globals) {
      const parsed = readFromObject(obj);
      if (parsed) return parsed;
    }

    try {
      const saved = JSON.parse(localStorage.getItem(STATE_KEY) || '{}');
      const restored = valid(saved?.size?.width, saved?.size?.height);
      if (restored) return restored;
    } catch (_) {}
    return DEFAULT_SIZE;
  }

  function isAllowedFamily(family = getFamily()) {
    if (BLOCKED_FAMILIES.has(family)) return false;
    return ALLOWED_FAMILIES.has(family);
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STATE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      regions = Array.isArray(parsed.regions) ? parsed.regions : [];
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (_) {
      regions = [];
      return {};
    }
  }

  function saveState(extra = {}) {
    const enabled = !!$('neo-scene-director-enabled')?.checked;
    const contracts = extra.contracts || (document.getElementById('neo-scene-count-contract') ? getPromptContracts() : undefined);
    const state = { enabled, regions, ...(contracts ? { contracts } : {}), ...extra };
    try { localStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (_) {}
    const stateNode = $('neo-scene-director-state');
    if (stateNode) stateNode.value = JSON.stringify(state);
    window.NeoSceneDirectorExtension.state = state;
    window.dispatchEvent(new CustomEvent('neo-scene-director-regions-updated', { detail: getSceneRegionTargets() }));
    if (window.NeoStudioApp?.generation?.workflow?.refreshLoraApplyTargets) window.NeoStudioApp.generation.workflow.refreshLoraApplyTargets();
    if ($('neo-scene-director-state')) syncPromptPayload();
  }

  function getSceneRegionTargets() {
    return regions.map((region, index) => normalizeRegionData(region, index))
      .filter(region => region.enabled && region.visible !== false)
      .map((region, index) => ({
        value: `scene_region_${index + 1}`,
        region_index: index + 1,
        id: region.id,
        label: region.label || `Region ${index + 1}`
      }));
  }

  async function fetchRecord() {
    try {
      const res = await fetch(`/api/extensions/packs?target_surface=image&workspace=assets&_=${Date.now()}`, { cache: 'no-store' });
      const data = await res.json();
      if (!data || !data.ok) return null;
      return (data.packs || []).find(pack => pack.extension_id === EXTENSION_ID || pack.id === EXTENSION_ID) || null;
    } catch (_) {
      return null;
    }
  }

  async function setExtensionEnabled(enabled) {
    try {
      const res = await fetch('/api/extensions/packs/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ extension_id: EXTENSION_ID, enabled: !!enabled }),
      });
      const data = await res.json();
      if (data && data.ok && data.record) registryRecord = data.record;
      setStatus(enabled ? summarizePromptReadiness() : 'Scene Director disabled. Normal Neo generation remains untouched.', enabled ? 'ok' : 'muted');
    } catch (_) {
      setStatus('Could not update the extension registry toggle. Local UI state was still saved.', 'warn');
    }
  }

  function setStatus(text, tone = 'muted') {
    const node = $('neo-scene-director-status');
    if (!node) return;
    node.textContent = text || '';
    node.dataset.tone = tone;
  }

  function canvasLabel(width, height) {
    if (width === height) return 'Square';
    return width > height ? 'Landscape' : 'Vertical';
  }


  function getMainPrompt() {
    return String($("generation-positive")?.value || $("generation-prompt")?.value || $("prompt")?.value || "").trim();
  }

  function getMainNegativePrompt() {
    return String($("generation-negative")?.value || $("generation-negative-prompt")?.value || $("negative-prompt")?.value || $("negative_prompt")?.value || "").trim();
  }

  function normalizeRegionData(region, index = 0) {
    const safe = region && typeof region === 'object' ? region : {};
    return {
      id: safe.id || 'region_' + Date.now() + '_' + index,
      label: String(safe.label || 'Person ' + (index + 1)),
      type: String(safe.type || 'character'),
      enabled: safe.enabled === false ? false : true,
      locked: safe.locked === true,
      visible: safe.visible === false ? false : true,
      prompt: String(safe.prompt || ''),
      negative_prompt: String(safe.negative_prompt || ''),
      strength: clamp(Number(safe.strength ?? 1), 0, 2),
      reference: String(safe.reference || 'off'),
      reference_note: String(safe.reference_note || ''),
      ipadapter_model: String(safe.ipadapter_model || ''),
      ipadapter_clip_vision: String(safe.ipadapter_clip_vision || 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'),
      ipadapter_weight: clamp(Number(safe.ipadapter_weight ?? 0.52), 0, 2),
      ipadapter_start_at: clamp(Number(safe.ipadapter_start_at ?? 0.05), 0, 1),
      ipadapter_end_at: clamp(Number(safe.ipadapter_end_at ?? 0.75), 0, 1),
      pose: String(safe.pose || 'off'),
      ipadapter: safe.ipadapter === true,
      ipadapter_slot: Math.max(1, Math.min(8, parseInt(safe.ipadapter_slot || safe.ipadapterSlot || (index + 1), 10) || (index + 1))),
      ipadapter_use_region_mask: safe.ipadapter_use_region_mask === false ? false : true,
      ipadapter_weight_mode: String(safe.ipadapter_weight_mode || 'slot_default'),
      rect: normalizeRegionRect(safe.rect, index),
      loras: Array.isArray(safe.loras) ? safe.loras : [],
    };
  }

  function getPromptContracts() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(STATE_KEY) || '{}') || {}; } catch (_) { saved = {}; }
    const savedContracts = saved.contracts && typeof saved.contracts === 'object' ? saved.contracts : {};
    const contracts = { ...DEFAULT_CONTRACTS, ...savedContracts };
    const enabledNode = $('neo-scene-contracts-enabled');
    const autoNode = $('neo-scene-node-auto-prompts');
    const countNode = $('neo-scene-count-contract');
    const subjectNode = $('neo-scene-subject-contract');
    const negativeNode = $('neo-scene-negative-contract');
    const styleNode = $('neo-scene-style-merge');
    return {
      enabled: enabledNode ? !!enabledNode.checked : contracts.enabled !== false,
      use_node_auto_prompts: autoNode ? !!autoNode.checked : contracts.use_node_auto_prompts === true,
      count_contract: String(countNode ? countNode.value : contracts.count_contract || '').trim(),
      subject_contract: String(subjectNode ? subjectNode.value : contracts.subject_contract || '').trim(),
      negative_contract: String(negativeNode ? negativeNode.value : contracts.negative_contract || '').trim(),
      style_merge: String(styleNode ? styleNode.value : contracts.style_merge || '').trim()
    };
  }

  function resetPromptContracts() {
    const map = {
      'neo-scene-contracts-enabled': DEFAULT_CONTRACTS.enabled,
      'neo-scene-node-auto-prompts': DEFAULT_CONTRACTS.use_node_auto_prompts,
      'neo-scene-count-contract': DEFAULT_CONTRACTS.count_contract,
      'neo-scene-subject-contract': DEFAULT_CONTRACTS.subject_contract,
      'neo-scene-negative-contract': DEFAULT_CONTRACTS.negative_contract,
      'neo-scene-style-merge': DEFAULT_CONTRACTS.style_merge
    };
    Object.entries(map).forEach(([id, value]) => {
      const node = $(id);
      if (!node) return;
      if (node.type === 'checkbox') node.checked = !!value;
      else node.value = String(value || '');
    });
    saveState({ contracts: getPromptContracts() });
    syncPromptPayload();
    setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted');
  }

  function getPromptPayload() {
    const { width, height } = getSize();
    const normalizedRegions = regions.map((region, index) => normalizeRegionData(region, index));
    const activeRegions = normalizedRegions.filter(region => region.enabled && region.visible !== false);
    return {
      version: 1,
      extension_id: EXTENSION_ID,
      enabled: !!$('neo-scene-director-enabled')?.checked,
      family: getFamily(),
      allowed: isAllowedFamily(),
      size: { width, height },
      global: { prompt: getMainPrompt(), negative_prompt: getMainNegativePrompt(), source: 'neo_image_tab' },
      contracts: getPromptContracts(),
      regions: normalizedRegions,
      active_region_count: activeRegions.length,
    };
  }

  function validatePromptPayload(payload = getPromptPayload()) {
    const warnings = [];
    if (payload.enabled && !payload.allowed) warnings.push('Scene Director only supports SDXL / SD 1.5.');
    if (payload.enabled && payload.active_region_count < 1) warnings.push('Add at least one enabled visible region.');
    const ipSlots = new Map();
    payload.regions.forEach((region, index) => {
      const label = region.label || 'Region ' + (index + 1);
      if (region.enabled && !String(region.prompt || '').trim()) warnings.push(label + ' has no region prompt.');
      if (region.enabled && region.ipadapter && !Number.isFinite(Number(region.ipadapter_slot))) warnings.push(label + ' IPAdapter slot binding is invalid.');
      if (region.enabled && region.ipadapter) {
        const slotKey = String(region.ipadapter_slot || '');
        if (ipSlots.has(slotKey)) warnings.push(label + ' shares IPAdapter slot ' + slotKey + ' with ' + ipSlots.get(slotKey) + '. Use one unique slot per region.');
        else ipSlots.set(slotKey, label);
      }
    });
    return warnings;
  }

  function summarizePromptReadiness() {
    const payload = getPromptPayload();
    const warnings = validatePromptPayload(payload);
    if (!payload.enabled) return 'Prompt system ready. Enable Scene Director when you want regions included in the future adapter payload.';
    if (warnings.length) return 'Prompt system needs attention: ' + warnings[0];
    return 'Prompt system ready: ' + payload.active_region_count + ' active region' + (payload.active_region_count === 1 ? '' : 's') + ' staged. SDXL / SD 1.5 V052 + IPAdapter slot binding adapter is active.';
  }

  function syncPromptPayload() {
    const payload = getPromptPayload();
    const stateNode = $('neo-scene-director-state');
    if (stateNode) stateNode.value = JSON.stringify(payload);
    const summary = $('neo-scene-director-prompt-summary');
    if (summary) {
      const warnings = validatePromptPayload(payload);
      summary.textContent = warnings.length ? warnings.join(' ') : 'Ready payload: ' + payload.active_region_count + ' active region' + (payload.active_region_count === 1 ? '' : 's') + ', global prompt linked from Neo.';
      summary.dataset.tone = warnings.length ? 'warn' : 'ok';
    }
    window.NeoSceneDirectorExtension.promptPayload = payload;
    return payload;
  }


  function resolveCanvasPreviewImageUrl() {
    const frame = $('neo-scene-director-canvas-frame');
    const inSceneDirector = (el) => !!(frame && el && frame.contains(el));
    const visible = (el) => {
      if (!el || inSceneDirector(el) || el.closest?.('#neo-scene-director-shell,[hidden],[aria-hidden="true"]')) return false;
      const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
      if (style && (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0)) return false;
      const rect = el.getBoundingClientRect?.();
      return !rect || (rect.width >= 48 && rect.height >= 48);
    };
    const srcOf = (el) => {
      const raw = el?.currentSrc || el?.src || el?.dataset?.src || el?.getAttribute?.('src') || '';
      const src = String(raw || '').trim();
      if (!src || src.startsWith('blob:') || src.includes('svg+xml')) return '';
      return src;
    };
    const preferredSelectors = [
      '#generation-preview img', '#image-preview img', '#neo-generation-preview img', '#active-output-preview img',
      '.generation-preview img', '.image-preview img', '.active-output img', '.selected-output img',
      '[data-output-selected="true"] img', '[data-selected="true"] img', '.result-card.selected img', '.output-card.selected img'
    ];
    for (const selector of preferredSelectors) {
      const nodes = Array.from(document.querySelectorAll(selector)).filter(visible);
      for (const img of nodes) {
        const src = srcOf(img);
        if (src) return src;
      }
    }
    const candidates = Array.from(document.querySelectorAll('img')).filter(visible)
      .map(img => ({ img, src: srcOf(img), rect: img.getBoundingClientRect?.() || { width: 0, height: 0 } }))
      .filter(item => item.src && !/logo|icon|avatar|emoji/i.test(item.src))
      .sort((a, b) => (b.rect.width * b.rect.height) - (a.rect.width * a.rect.height));
    return candidates[0]?.src || '';
  }

  function syncCanvasPreviewBackground() {
    const frame = $('neo-scene-director-canvas-frame');
    if (!frame) return;
    const url = resolveCanvasPreviewImageUrl();
    if (!url) return;
    frame.style.backgroundImage = `linear-gradient(rgba(8, 20, 36, .32), rgba(8, 20, 36, .32)), url("${String(url).replace(/"/g, '%22')}")`;
    frame.style.backgroundSize = 'contain';
    frame.style.backgroundPosition = 'center center';
    frame.style.backgroundRepeat = 'no-repeat';
    frame.dataset.hasPreviewImage = 'true';
  }

  function updateCanvasShell() {
    const frame = $('neo-scene-director-canvas-frame');
    const meta = $('neo-scene-director-canvas-meta');
    if (!frame) return;
    const { width, height } = getSize();
    frame.style.aspectRatio = `${width} / ${height}`;
    frame.style.width = '100%';
    frame.style.height = 'auto';
    frame.style.maxHeight = 'none';
    frame.dataset.canvasWidth = String(width);
    frame.dataset.canvasHeight = String(height);
    frame.dataset.orientation = canvasLabel(width, height).toLowerCase();
    if (meta) meta.textContent = `${width} × ${height} · ${canvasLabel(width, height)} preview shell`;
    renderGhostBoxes(width, height);
    syncCanvasPreviewBackground();
    saveState({ size: { width, height } });
  }

  function normalizeRect(index) {
    const presets = [
      { x: 0.08, y: 0.14, w: 0.28, h: 0.70 },
      { x: 0.36, y: 0.12, w: 0.28, h: 0.72 },
      { x: 0.64, y: 0.14, w: 0.28, h: 0.70 },
    ];
    return presets[index % presets.length];
  }

  function addRegion() {
    const index = regions.length;
    regions.push(normalizeRegionData({
      id: `region_${Date.now()}`,
      label: `Person ${index + 1}`,
      type: 'character',
      enabled: true,
      locked: false,
      visible: true,
      prompt: '',
      negative_prompt: '',
      strength: 1,
      reference: 'off',
      reference_note: '',
      ipadapter_model: '',
      ipadapter_clip_vision: 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors',
      ipadapter_weight: 0.52,
      ipadapter_start_at: 0.05,
      ipadapter_end_at: 0.75,
      pose: 'off',
      ipadapter: false,
      ipadapter_slot: index + 1,
      ipadapter_use_region_mask: true,
      ipadapter_weight_mode: 'slot_default',
      lora: false,
      lora_slot: index + 1,
      lora_weight_mode: 'slot_default',
      lora_strength: 0.8,
      rect: normalizeRect(index),
      loras: [],
    }, index));
    renderRegions();
    updateCanvasShell();
    saveState();
  }

  function removeRegion(id) {
    regions = regions.filter(region => region.id !== id);
    renderRegions();
    updateCanvasShell();
    saveState();
  }

  function updateRegion(id, patch) {
    regions = regions.map(region => region.id === id ? { ...region, ...patch } : region);
    renderGhostBoxes();
    saveState();
  }

  function clamp(value, min = 0, max = 1) {
    return Math.max(min, Math.min(max, Number.isFinite(value) ? value : min));
  }

  function normalizeRegionRect(rect, fallbackIndex = 0) {
    const fallback = normalizeRect(fallbackIndex);
    let x = clamp(Number(rect?.x ?? fallback.x));
    let y = clamp(Number(rect?.y ?? fallback.y));
    let w = clamp(Number(rect?.w ?? fallback.w), MIN_RECT_SIZE, 1);
    let h = clamp(Number(rect?.h ?? fallback.h), MIN_RECT_SIZE, 1);
    if (x + w > 1) x = Math.max(0, 1 - w);
    if (y + h > 1) y = Math.max(0, 1 - h);
    return { x, y, w, h };
  }

  function getRegion(id) {
    return regions.find(region => region.id === id) || null;
  }

  function setSelectedRegion(id) {
    selectedRegionId = id || null;
    document.querySelectorAll('.neo-scene-director-region-box').forEach(box => {
      box.dataset.selected = box.dataset.regionId === selectedRegionId ? 'true' : 'false';
    });
    document.querySelectorAll('.neo-scene-director-region-card').forEach(card => {
      card.dataset.selected = card.dataset.regionId === selectedRegionId ? 'true' : 'false';
    });
  }

  function applyRectToRegion(id, rect) {
    const region = getRegion(id);
    if (!region) return;
    region.rect = normalizeRegionRect(rect);
    const box = document.querySelector(`.neo-scene-director-region-box[data-region-id="${CSS.escape(id)}"]`);
    if (box) applyRectToBox(box, region.rect);
    saveState();
  }

  function applyRectToBox(box, rect) {
    const safe = normalizeRegionRect(rect);
    box.style.left = `${safe.x * 100}%`;
    box.style.top = `${safe.y * 100}%`;
    box.style.width = `${safe.w * 100}%`;
    box.style.height = `${safe.h * 100}%`;
  }

  function makeResizeHandles(region) {
    return ['nw', 'ne', 'sw', 'se'].map(handle =>
      `<button type="button" class="neo-scene-director-resize-handle neo-scene-director-resize-${handle}" data-region-resize="${region.id}" data-handle="${handle}" aria-label="Resize ${escapeHtml(region.label || 'region')} ${handle}"></button>`
    ).join('');
  }

  function renderGhostBoxes() {
    const layer = $('neo-scene-director-region-layer');
    if (!layer) return;
    layer.innerHTML = '';
    regions.filter(region => region.visible !== false).forEach((region, index) => {
      region.rect = normalizeRegionRect(region.rect, index);
      const box = makeEl('div', 'neo-scene-director-region-box', `
        <span>${escapeHtml(region.label || `Region ${index + 1}`)}</span>
        ${makeResizeHandles(region)}
      `);
      box.tabIndex = 0;
      box.dataset.regionId = region.id;
      box.dataset.enabled = region.enabled === false ? 'false' : 'true';
      box.dataset.locked = region.locked === true ? 'true' : 'false';
      box.dataset.selected = region.id === selectedRegionId ? 'true' : 'false';
      box.title = region.locked ? 'Region locked' : 'Drag to move. Resize from the corners.';
      applyRectToBox(box, region.rect);
      layer.appendChild(box);
    });
    if (selectedRegionId && !getRegion(selectedRegionId)) selectedRegionId = null;
    setSelectedRegion(selectedRegionId);
  }

  function beginInteraction(event, id, mode, handle = null) {
    const frame = $('neo-scene-director-canvas-frame');
    const region = getRegion(id);
    if (!frame || !region || region.locked) return;
    event.preventDefault();
    event.stopPropagation();
    setSelectedRegion(id);
    const bounds = frame.getBoundingClientRect();
    const startRect = normalizeRegionRect(region.rect);
    activeInteraction = {
      id,
      mode,
      handle,
      bounds,
      startX: event.clientX,
      startY: event.clientY,
      startRect,
      pointerId: event.pointerId,
    };
    try { event.currentTarget.setPointerCapture?.(event.pointerId); } catch (_) {}
    document.body.classList.add('neo-scene-director-dragging');
  }

  function rectFromInteraction(event) {
    if (!activeInteraction) return null;
    const { bounds, startX, startY, startRect, mode, handle } = activeInteraction;
    const dx = (event.clientX - startX) / Math.max(1, bounds.width);
    const dy = (event.clientY - startY) / Math.max(1, bounds.height);
    let { x, y, w, h } = startRect;

    if (mode === 'move') {
      x = clamp(startRect.x + dx, 0, 1 - startRect.w);
      y = clamp(startRect.y + dy, 0, 1 - startRect.h);
      return { x, y, w, h };
    }

    if (mode === 'resize') {
      const fromLeft = handle.includes('w');
      const fromTop = handle.includes('n');
      const fromRight = handle.includes('e');
      const fromBottom = handle.includes('s');

      let left = startRect.x;
      let top = startRect.y;
      let right = startRect.x + startRect.w;
      let bottom = startRect.y + startRect.h;

      if (fromLeft) left = clamp(startRect.x + dx, 0, right - MIN_RECT_SIZE);
      if (fromRight) right = clamp(startRect.x + startRect.w + dx, left + MIN_RECT_SIZE, 1);
      if (fromTop) top = clamp(startRect.y + dy, 0, bottom - MIN_RECT_SIZE);
      if (fromBottom) bottom = clamp(startRect.y + startRect.h + dy, top + MIN_RECT_SIZE, 1);

      x = left; y = top; w = right - left; h = bottom - top;

      if (event.shiftKey) {
        const ratio = startRect.w / Math.max(MIN_RECT_SIZE, startRect.h);
        if (w / Math.max(MIN_RECT_SIZE, h) > ratio) w = h * ratio;
        else h = w / ratio;
        if (fromLeft) x = right - w;
        if (fromTop) y = bottom - h;
      }

      if (event.altKey) {
        const cx = startRect.x + startRect.w / 2;
        const cy = startRect.y + startRect.h / 2;
        x = clamp(cx - w / 2, 0, 1 - w);
        y = clamp(cy - h / 2, 0, 1 - h);
      }
      return normalizeRegionRect({ x, y, w, h });
    }
    return null;
  }

  function endInteraction() {
    if (!activeInteraction) return;
    activeInteraction = null;
    document.body.classList.remove('neo-scene-director-dragging');
  }

  function option(value, current, label) {
    return '<option value="' + escapeHtml(value) + '" ' + (String(current || '') === String(value) ? 'selected' : '') + '>' + escapeHtml(label) + '</option>';
  }

  function renderRegions() {
    const host = $('neo-scene-director-regions-host');
    if (!host) return;
    regions = regions.map((region, index) => normalizeRegionData(region, index));
    if (!regions.length) {
      host.innerHTML = '<div class="mini-note">No regions yet. Add one, then drag the box, resize from the corners, and add a region prompt.</div>';
      syncPromptPayload();
      return;
    }
    host.innerHTML = '';
    regions.forEach((region, index) => {
      const card = makeEl('div', 'neo-scene-director-region-card');
      card.dataset.regionId = region.id;
      card.dataset.selected = region.id === selectedRegionId ? 'true' : 'false';
      card.innerHTML = `
        <div class="row-between" style="gap:10px; align-items:center;">
          <div class="row" style="gap:8px; align-items:center; flex-wrap:wrap;">
            <input type="checkbox" data-region-enabled="${region.id}" ${region.enabled === false ? '' : 'checked'} title="Enable this region for the future adapter payload" />
            <input class="neo-scene-director-label-input" data-region-label="${region.id}" value="${escapeHtml(region.label || `Person ${index + 1}`)}" />
            <select data-region-type="${region.id}" title="Region type">
              ${option('character', region.type, 'Character')}
              ${option('object', region.type, 'Object')}
              ${option('background', region.type, 'Background')}
              ${option('style', region.type, 'Style area')}
            </select>
          </div>
          <div class="row" style="gap:8px; flex-wrap:wrap;">
            <button class="btn btn-small" type="button" data-region-lock="${region.id}">${region.locked ? 'Unlock' : 'Lock'}</button>
            <button class="btn btn-small" type="button" data-region-visible="${region.id}">${region.visible === false ? 'Show' : 'Hide'}</button>
            <button class="btn btn-small" type="button" data-region-copy="${region.id}">Duplicate</button>
            <button class="btn btn-small" type="button" data-region-remove="${region.id}">Delete</button>
          </div>
        </div>
        <div class="grid grid-2" style="margin-top:10px; gap:10px;">
          <div>
            <label for="neo-scene-prompt-${region.id}">Region prompt</label>
            <textarea id="neo-scene-prompt-${region.id}" data-region-prompt="${region.id}" rows="4" placeholder="Prompt only for this region. Neo main prompt stays global.">${escapeHtml(region.prompt || '')}</textarea>
          </div>
          <div>
            <label for="neo-scene-negative-${region.id}">Region negative prompt</label>
            <textarea id="neo-scene-negative-${region.id}" data-region-negative="${region.id}" rows="4" placeholder="Optional negative prompt only for this region.">${escapeHtml(region.negative_prompt || '')}</textarea>
          </div>
        </div>
        <div class="grid grid-2" style="margin-top:10px; gap:10px; align-items:end;">
          <div>
            <label>Prompt strength</label>
            <input type="number" step="0.05" min="0" max="2" data-region-strength="${region.id}" value="${Number(region.strength || 1)}" />
          </div>
          <div class="mini-note">ControlNet stays global. Use the normal Neo ControlNet panel for Canny, OpenPose, Depth, etc.</div>
        </div>
        <div class="neo-scene-ipadapter-panel" style="margin-top:10px; padding:10px; border:1px solid rgba(148,163,184,.16); border-radius:12px; background:rgba(15,23,42,.24);" data-enabled="${region.ipadapter ? 'true' : 'false'}">
          <div class="row-between" style="gap:10px; align-items:center;">
            <div>
              <label class="neo-toggle-line"><input type="checkbox" data-region-ipadapter="${region.id}" ${region.ipadapter ? 'checked' : ''}/> Use IPAdapter for this region</label>
              <div class="muted small">Reference image/model stays in the main Neo IPAdapter slot. Scene Director only binds that slot to this region mask.</div>
            </div>
            <span class="badge">Region mask</span>
          </div>
          <div class="grid grid-4" style="margin-top:10px; gap:10px; align-items:end; opacity:${region.ipadapter ? '1' : '.45'};">
            <div>
              <label>Neo IPAdapter slot</label>
              <select data-region-ip-slot="${region.id}" ${region.ipadapter ? '' : 'disabled'}>
                ${[1,2,3,4,5,6,7,8].map(slot => option(String(slot), String(region.ipadapter_slot || (index + 1)), 'IPAdapter ' + slot)).join('')}
              </select>
            </div>
            <div>
              <label>Weight source</label>
              <select data-region-ip-weight-mode="${region.id}" ${region.ipadapter ? '' : 'disabled'}>
                ${option('slot_default', region.ipadapter_weight_mode, 'Use slot default')}
                ${option('custom', region.ipadapter_weight_mode, 'Custom override')}
              </select>
            </div>
            <div>
              <label>Custom weight</label>
              <input type="number" step="0.01" min="0" max="2" data-region-ip-weight="${region.id}" value="${Number(region.ipadapter_weight ?? 0.52)}" ${region.ipadapter ? '' : 'disabled'} />
            </div>
            <div>
              <label class="neo-toggle-line"><input type="checkbox" data-region-ip-mask="${region.id}" ${region.ipadapter_use_region_mask === false ? '' : 'checked'} ${region.ipadapter ? '' : 'disabled'} /> Use region mask</label>
            </div>
          </div>
          <div class="mini-note" style="margin-top:8px;">When Scene Director is ON, normal global IPAdapter is suppressed. Only region-bound IPAdapter slots are applied to prevent face bleed.</div>
        </div>
        `;
      host.appendChild(card);
    });
    syncPromptPayload();
  }

  function duplicateRegion(id) {
    const source = regions.find(region => region.id === id);
    if (!source) return;
    regions.push({ ...source, id: `region_${Date.now()}`, label: `${source.label || 'Region'} Copy`, rect: normalizeRegionRect({ ...(source.rect || normalizeRect(0)), x: (source.rect?.x || 0) + 0.04, y: (source.rect?.y || 0) + 0.04 }) });
    renderRegions();
    updateCanvasShell();
    saveState();
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function bindRegionEvents(root) {
    root.addEventListener('input', event => {
      const target = event.target;
      if (!target) return;
      const labelId = target.getAttribute('data-region-label');
      const promptId = target.getAttribute('data-region-prompt');
      const negativeId = target.getAttribute('data-region-negative');
      const strengthId = target.getAttribute('data-region-strength');
      const refNoteId = target.getAttribute('data-region-ref-note');
      const ipModelId = target.getAttribute('data-region-ip-model');
      const ipClipId = target.getAttribute('data-region-ip-clip');
      const ipWeightId = target.getAttribute('data-region-ip-weight');
      const ipStartId = target.getAttribute('data-region-ip-start');
      const ipEndId = target.getAttribute('data-region-ip-end');
      const ipSlotId = target.getAttribute('data-region-ip-slot');
      const ipWeightModeId = target.getAttribute('data-region-ip-weight-mode');
      if (labelId) updateRegion(labelId, { label: target.value });
      if (promptId) updateRegion(promptId, { prompt: target.value });
      if (negativeId) updateRegion(negativeId, { negative_prompt: target.value });
      if (strengthId) updateRegion(strengthId, { strength: clamp(Number(target.value || 1), 0, 2) });
      if (refNoteId) updateRegion(refNoteId, { reference_note: target.value });
      if (ipModelId) updateRegion(ipModelId, { ipadapter_model: target.value });
      if (ipClipId) updateRegion(ipClipId, { ipadapter_clip_vision: target.value });
      if (ipWeightId) updateRegion(ipWeightId, { ipadapter_weight: clamp(Number(target.value || 0.52), 0, 2) });
      if (ipStartId) updateRegion(ipStartId, { ipadapter_start_at: clamp(Number(target.value || 0.05), 0, 1) });
      if (ipEndId) updateRegion(ipEndId, { ipadapter_end_at: clamp(Number(target.value || 0.75), 0, 1) });
      if (ipSlotId) updateRegion(ipSlotId, { ipadapter_slot: Math.max(1, Math.min(8, parseInt(target.value || '1', 10) || 1)) });
      if (ipWeightModeId) updateRegion(ipWeightModeId, { ipadapter_weight_mode: target.value || 'slot_default' });
      if (loraStrengthId) updateRegion(loraStrengthId, { lora_strength: clamp(Number(target.value || 0.8), -4, 4) });
      if (loraSlotId) updateRegion(loraSlotId, { lora_slot: Math.max(1, Math.min(8, parseInt(target.value || '1', 10) || 1)) });
      if (loraWeightModeId) updateRegion(loraWeightModeId, { lora_weight_mode: target.value || 'slot_default' });
      setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted');
    });
    root.addEventListener('change', event => {
      const target = event.target;
      const enabledId = target?.getAttribute('data-region-enabled');
      const typeId = target?.getAttribute('data-region-type');
      const refId = target?.getAttribute('data-region-ref');
      const poseId = target?.getAttribute('data-region-pose');
      const ipadapterId = target?.getAttribute('data-region-ipadapter');
      const ipMaskId = target?.getAttribute('data-region-ip-mask');
      const loraId = target?.getAttribute('data-region-lora');
      if (enabledId) updateRegion(enabledId, { enabled: !!target.checked });
      if (typeId) updateRegion(typeId, { type: target.value || 'character' });
      if (refId) updateRegion(refId, { reference: target.value || 'off' });
      if (poseId) updateRegion(poseId, { pose: target.value || 'off' });
      if (ipadapterId) { updateRegion(ipadapterId, { ipadapter: !!target.checked }); renderRegions(); }
      if (ipMaskId) updateRegion(ipMaskId, { ipadapter_use_region_mask: !!target.checked });
      setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted');
    });
    root.addEventListener('click', event => {
      const target = event.target;
      const removeId = target?.getAttribute('data-region-remove');
      const copyId = target?.getAttribute('data-region-copy');
      const lockId = target?.getAttribute('data-region-lock');
      const visibleId = target?.getAttribute('data-region-visible');
      const card = target?.closest?.('.neo-scene-director-region-card');
      if (card?.dataset?.regionId && !removeId && !copyId && !lockId && !visibleId) setSelectedRegion(card.dataset.regionId);
      if (removeId) removeRegion(removeId);
      if (copyId) duplicateRegion(copyId);
      if (lockId) { const region = getRegion(lockId); if (region) updateRegion(lockId, { locked: !region.locked }); renderRegions(); updateCanvasShell(); }
      if (visibleId) { const region = getRegion(visibleId); if (region) updateRegion(visibleId, { visible: region.visible === false }); renderRegions(); updateCanvasShell(); }
      setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted');
    });
  }

  function updateEligibility() {
    const family = getFamily();
    const allowed = isAllowedFamily(family);
    const shell = $('neo-scene-director-shell');
    const familyBadge = $('neo-scene-director-family-badge');
    const enabledInput = $('neo-scene-director-enabled');
    if (shell) shell.dataset.familyAllowed = allowed ? 'true' : 'false';
    if (familyBadge) familyBadge.textContent = allowed ? 'SD / SDXL ready' : `${family || 'family'} blocked`;
    if (enabledInput && !allowed) enabledInput.checked = false;
    setStatus(allowed ? summarizePromptReadiness() : 'Scene Director is blocked for this family. Flux, Qwen, and Z-Image stay untouched.', allowed ? 'muted' : 'warn');
    saveState({ family });
  }

  function mountShell(parent) {
    if (!parent || $('neo-scene-director-shell')) return;
    const saved = loadState();
    const shell = makeEl('details', 'accordion-block generation-inline-accordion neo-scene-director-shell');
    shell.id = 'neo-scene-director-shell';
    shell.open = false;
    shell.innerHTML = `
      <summary class="accordion-summary">
        <div>
          <div class="accordion-title">Scene Director</div>
          <div class="accordion-hint">Regional prompting UI shell for SD / SDXL. Uses Neo main prompt and image settings as the global base.</div>
        </div>
        <span class="badge" id="neo-scene-director-family-badge">SD / SDXL ready</span>
        <span class="accordion-chevron" aria-hidden="true">▾</span>
      </summary>
      <div class="accordion-body">
        <div class="neo-scene-director-topbar">
          <label class="neo-toggle-line"><input id="neo-scene-director-enabled" type="checkbox" ${saved.enabled ? 'checked' : ''}/> Enable Scene Director</label>
          <span class="badge">IPAdapter slot binding</span>
        </div>
        <div class="mini-note" id="neo-scene-director-status">Loading Scene Director shell...</div>
        <input id="neo-scene-director-state" type="hidden" value="" />
        <div class="neo-scene-director-layout">
          <div class="neo-scene-director-canvas-wrap">
            <div class="row-between" style="gap:12px; align-items:flex-start;">
              <div>
                <div class="stat-title">Canvas regional editor</div>
                <div class="muted small" id="neo-scene-director-canvas-meta">Matches Neo output size.</div>
              </div>
              <button class="btn btn-small" id="neo-scene-director-add-region" type="button">+ Add Region</button>
            </div>
            <div class="neo-scene-director-canvas-frame" id="neo-scene-director-canvas-frame">
              <div class="neo-scene-director-region-layer" id="neo-scene-director-region-layer"></div>
              <div class="neo-scene-director-canvas-empty">Drag boxes to move. Use corner handles to resize.</div>
            </div>
          </div>
          <div class="neo-scene-director-global-card">
            <details class="neo-scene-linked-inputs-collapse" id="neo-scene-linked-inputs-collapse">
              <summary class="row-between" style="cursor:pointer; gap:10px; align-items:center; list-style:none;">
                <div>
                  <div class="stat-title">Neo-linked inputs</div>
                  <div class="muted small">Prompt/contracts and Neo input routing. Expand only when editing contracts.</div>
                </div>
                <span class="badge">Expand</span>
              </summary>
              <div class="neo-scene-director-chip-grid" style="margin-top:10px;">
                <span>Main prompt: global</span>
                <span>Negative: global</span>
                <span>Sampler/settings: Neo</span>
                <span>Preview/output: Neo</span>
              </div>
            <div class="neo-scene-contract-panel" style="margin-top:12px; padding:12px; border:1px solid rgba(148,163,184,.18); border-radius:14px; background:rgba(15,23,42,.34);">
              <div class="row-between" style="gap:10px; align-items:center;">
                <div>
                  <div class="stat-title">Prompt Contracts</div>
                  <div class="muted small">Editable structure text. No hidden gender, body type, couple type, or style is injected by Neo.</div>
                </div>
                <button class="btn btn-small" type="button" id="neo-scene-reset-contracts">Reset Defaults</button>
              </div>
              <div class="grid grid-2" style="gap:10px; margin-top:10px;">
                <label class="neo-toggle-line"><input type="checkbox" id="neo-scene-contracts-enabled" ${((saved.contracts || {}).enabled === false) ? '' : 'checked'} /> Enable editable contracts</label>
                <label class="neo-toggle-line"><input type="checkbox" id="neo-scene-node-auto-prompts" ${((saved.contracts || {}).use_node_auto_prompts === true) ? 'checked' : ''} /> Use V052 node auto prompts</label>
              </div>
              <label style="margin-top:10px; display:block;">Count contract</label>
              <textarea id="neo-scene-count-contract" rows="2" placeholder="exactly {count} visible subjects...">${escapeHtml((saved.contracts || {}).count_contract || DEFAULT_CONTRACTS.count_contract)}</textarea>
              <label style="margin-top:10px; display:block;">Subject contract</label>
              <textarea id="neo-scene-subject-contract" rows="2" placeholder="one complete subject inside this region...">${escapeHtml((saved.contracts || {}).subject_contract || DEFAULT_CONTRACTS.subject_contract)}</textarea>
              <label style="margin-top:10px; display:block;">Negative contract</label>
              <textarea id="neo-scene-negative-contract" rows="2" placeholder="extra people, missing subject...">${escapeHtml((saved.contracts || {}).negative_contract || DEFAULT_CONTRACTS.negative_contract)}</textarea>
              <label style="margin-top:10px; display:block;">Style merge note</label>
              <textarea id="neo-scene-style-merge" rows="2" placeholder="use Neo main prompt as scene style...">${escapeHtml((saved.contracts || {}).style_merge || DEFAULT_CONTRACTS.style_merge)}</textarea>
              <div class="mini-note" style="margin-top:8px;">Use <code>{count}</code> inside contracts. Identity/gender/body words should live in your main or region prompts only.</div>
            </div>
            <div class="mini-note" id="neo-scene-director-prompt-summary" style="margin-top:10px;">Prompt payload will be staged here.</div><div class="mini-note" style="margin-top:10px;">LoRA per region is intentionally staged until the backend node patch lands.</div>
          </div>
        </div>
        <div class="neo-scene-director-region-list-head row-between">
          <div>
            <div class="stat-title">Regions</div>
            <div class="muted small">Controls live below the canvas so the right-side Prompt Stack and Image Preview shell stay intact.</div>
          </div>
        </div>
        <div id="neo-scene-director-regions-host"></div>
      </div>`;
    parent.prepend(shell);
    bindRegionEvents(shell);
    $('neo-scene-director-add-region')?.addEventListener('click', addRegion);
    const layer = $('neo-scene-director-region-layer');
    layer?.addEventListener('pointerdown', event => {
      const handle = event.target?.closest?.('[data-region-resize]');
      if (handle) { beginInteraction(event, handle.getAttribute('data-region-resize'), 'resize', handle.getAttribute('data-handle') || 'se'); return; }
      const box = event.target?.closest?.('.neo-scene-director-region-box');
      if (box?.dataset?.regionId) beginInteraction(event, box.dataset.regionId, 'move');
    });
    window.addEventListener('pointermove', event => {
      if (!activeInteraction) return;
      const rect = rectFromInteraction(event);
      if (rect) applyRectToRegion(activeInteraction.id, rect);
    });
    window.addEventListener('pointerup', endInteraction);
    window.addEventListener('pointercancel', endInteraction);
    shell.addEventListener('keydown', event => {
      if (!selectedRegionId || ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target?.tagName)) return;
      const region = getRegion(selectedRegionId);
      if (!region || region.locked) return;
      const step = event.shiftKey ? 0.025 : 0.006;
      const rect = normalizeRegionRect(region.rect);
      if (event.key === 'ArrowLeft') rect.x -= step;
      else if (event.key === 'ArrowRight') rect.x += step;
      else if (event.key === 'ArrowUp') rect.y -= step;
      else if (event.key === 'ArrowDown') rect.y += step;
      else return;
      event.preventDefault();
      applyRectToRegion(selectedRegionId, rect);
    });
    $('neo-scene-director-enabled')?.addEventListener('change', event => {
      const enabled = !!event.target.checked;
      if (!isAllowedFamily()) {
        event.target.checked = false;
        updateEligibility();
        return;
      }
      saveState();
      setExtensionEnabled(enabled);
    });
    ['generation-width', 'generation-height', 'width', 'height', 'txt2img-width', 'txt2img-height', 'image-width', 'image-height', 'neo-width', 'neo-height', 'neo-generation-width', 'neo-generation-height', 'generation-size', 'generation-size-preset', 'generation-resolution', 'image-resolution'].forEach(id => {
      $(id)?.addEventListener('input', updateCanvasShell);
      $(id)?.addEventListener('change', updateCanvasShell);
    });
    document.addEventListener('input', (event) => {
      const target = event.target;
      const key = String(target?.id || target?.name || '').toLowerCase();
      if (key.includes('width') || key.includes('height') || key.includes('size')) updateCanvasShell();
    });
    document.addEventListener('change', (event) => {
      const target = event.target;
      const key = String(target?.id || target?.name || target?.className || target?.getAttribute?.('aria-label') || '').toLowerCase();
      if (key.includes('width') || key.includes('height') || key.includes('size') || key.includes('resolution') || key.includes('aspect')) updateCanvasShell();
      else window.setTimeout(updateCanvasShell, 50);
    });
    document.addEventListener('click', () => window.setTimeout(() => { updateCanvasShell(); syncCanvasPreviewBackground(); }, 80), true);
    window.addEventListener('neo-scene-director-size-changed', () => window.setTimeout(updateCanvasShell, 20));
    window.addEventListener('neo-image-state-changed', () => window.setTimeout(() => { updateCanvasShell(); syncCanvasPreviewBackground(); }, 20));
    installGenerationSizeBridge();
    let lastCanvasSizeKey = '';
    window.setInterval(() => {
      const size = getSize();
      const key = `${size.width}x${size.height}`;
      if (key !== lastCanvasSizeKey) {
        lastCanvasSizeKey = key;
        updateCanvasShell();
      }
    }, 700);
    ['generation-positive', 'generation-negative', 'generation-prompt', 'prompt', 'generation-negative-prompt', 'negative-prompt', 'negative_prompt'].forEach(id => $(id)?.addEventListener('input', () => { syncPromptPayload(); setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted'); }));
    ['neo-scene-contracts-enabled', 'neo-scene-node-auto-prompts', 'neo-scene-count-contract', 'neo-scene-subject-contract', 'neo-scene-negative-contract', 'neo-scene-style-merge'].forEach(id => $(id)?.addEventListener('input', () => { saveState({ contracts: getPromptContracts() }); syncPromptPayload(); setStatus(summarizePromptReadiness(), validatePromptPayload().length ? 'warn' : 'muted'); }));
    $('neo-scene-reset-contracts')?.addEventListener('click', resetPromptContracts);
    document.addEventListener('neo-generation-family-changed', updateEligibility);
    renderRegions();
    updateCanvasShell();
    updateEligibility();
  }

  async function init() {
    if (mounted) return;
    const host = $('generation-assets-tab-host');
    if (!host) return;
    mounted = true;
    registryRecord = await fetchRecord();
    mountShell(host);
    if (registryRecord && $('neo-scene-director-enabled')) {
      $('neo-scene-director-enabled').checked = !!registryRecord.enabled || !!loadState().enabled;
      saveState({ registry_enabled: !!registryRecord.enabled });
    }
  }

  function retryInit(attempt = 0) {
    if ($('generation-assets-tab-host')) { init(); return; }
    if (attempt > 40) return;
    window.setTimeout(() => retryInit(attempt + 1), 125);
  }

  window.NeoSceneDirectorExtension = {
    id: EXTENSION_ID,
    phase: 9.3,
    ready: true,
    mount: init,
    getState: () => getPromptPayload(),
    getRegionTargets: () => getSceneRegionTargets(),
    validate: () => validatePromptPayload(),
  };

  ready(() => ensureCanonicalImageState(() => retryInit()));
})();
