(function () {
  const ROOT_SELECTOR = '#tab-generate';
  const SECTION_STATUS = {
    ready: { label: 'Ready', tone: 'ok' },
    warn: { label: 'Needs setup', tone: 'warn' },
    missing: { label: 'Missing setup', tone: 'danger' },
    info: { label: 'Guided', tone: 'info' },
    experimental: { label: 'Experimental', tone: 'purple' },
  };

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) {
    return document.getElementById(id);
  }

  function runtime() {
    return window.NeoStudioApp?.generation?.getRuntime?.() || window.NeoGenerationRuntime || null;
  }

  function normalizeTitle(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function boolFromSelect(id) {
    return String($(id)?.value || 'false') === 'true';
  }

  function hasFiles(id) {
    return !!($(id)?.files && $(id).files.length);
  }

  function numberValue(id, fallback=0) {
    const raw = Number($(id)?.value || fallback);
    return Number.isFinite(raw) ? raw : fallback;
  }

  function createWarningPanel() {
    const foundation = $('generation-ux-foundation-bar');
    if (!foundation || $('generation-ux-warning-panel')) return;
    foundation.insertAdjacentHTML('afterend', `
      <div class="neo-warning-panel" id="generation-ux-warning-panel">
        <div class="neo-warning-header">
          <div>
            <div class="neo-warning-title">Reliability & clarity</div>
            <div class="neo-warning-subtitle">Live setup checks, dependency audit, and beginner-safe warnings before you burn time on bad runs.</div>
          </div>
          <div class="neo-warning-actions">
            <button class="btn btn-small" id="btn-generation-ux-refresh-catalog" type="button">Refresh catalog</button>
            <button class="btn btn-small" id="btn-generation-ux-refresh-detailers" type="button">Refresh detailers</button>
            <button class="btn btn-small" id="btn-generation-ux-refresh-audit" type="button">Refresh audit</button>
            <button class="btn btn-small" id="btn-generation-ux-open-admin" type="button">Open Admin</button>
          </div>
        </div>
        <div class="neo-warning-list" id="generation-ux-warning-list"></div>
      </div>`);
    $('btn-generation-ux-refresh-catalog')?.addEventListener('click', () => runtime()?.refreshCatalog?.(true));
    $('btn-generation-ux-refresh-detailers')?.addEventListener('click', () => runtime()?.refreshDetailerModels?.(true));
    $('btn-generation-ux-refresh-audit')?.addEventListener('click', () => runtime()?.refreshDependencyAudit?.({ force:true }));
    $('btn-generation-ux-open-admin')?.addEventListener('click', () => {
      document.querySelector('[data-main-tab="admin"]')?.click();
      document.querySelector('[data-main-tab="admin"]')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  function baseCapabilityChip(container) {
    let chip = container.querySelector('.neo-capability-chip');
    if (!chip) {
      chip = document.createElement('span');
      chip.className = 'neo-guide-chip neo-capability-chip';
      container.prepend(chip);
    }
    return chip;
  }

  function resolveSectionState(title) {
    const rt = runtime();
    const session = rt?.getImageSession?.() || { connected: false };
    const catalog = rt?.getCatalogState?.() || {};
    const detailer = rt?.getDetailerCatalog?.() || {};
    const features = catalog.features || {};
    const checkpoints = Array.isArray(catalog.checkpoints) ? catalog.checkpoints : [];
    const loras = Array.isArray(catalog.loras) ? catalog.loras : [];
    const controlnets = Array.isArray(catalog.controlnet) ? catalog.controlnet : [];
    const ipModels = Array.isArray(catalog.ipadapter) ? catalog.ipadapter : [];
    const clipVision = Array.isArray(catalog.clip_vision) ? catalog.clip_vision : [];
    const samCount = (detailer.sam_models || []).length;
    const detCount = (detailer.bbox_models || []).length + (detailer.segm_models || []).length;
    const key = normalizeTitle(title);

    if (key === 'core generation') {
      if (!session.connected) return { tone: 'danger', label: 'No backend' };
      if (!checkpoints.length) return { tone: 'warn', label: 'No checkpoints' };
      return { tone: 'ok', label: 'Ready' };
    }
    if (key === 'upscale lab') {
      if (!session.connected || !checkpoints.length) return { tone: 'warn', label: 'Needs model' };
      return { tone: 'ok', label: 'Ready' };
    }
    if (key === 'supir restoration') {
      if (!features.supir_upscale) return { tone: 'warn', label: 'SUPIR node missing' };
      if (!checkpoints.length) return { tone: 'warn', label: 'Pick models' };
      return { tone: 'purple', label: 'Heavy / ready' };
    }
    if (key === 'lora settings') {
      if (!loras.length) return { tone: 'warn', label: 'No LoRAs scanned' };
      return { tone: 'ok', label: `${loras.length} available` };
    }
    if (key === 'embeddings') {
      return { tone: 'info', label: 'Manual setup' };
    }
    if (key === 'selective repair') {
      if (!detCount && !samCount) return { tone: 'warn', label: 'No detailer models' };
      if (!detCount || !samCount) return { tone: 'warn', label: 'Partial setup' };
      return { tone: 'purple', label: 'Experimental / ready' };
    }
    if (key === 'controlnet settings') {
      if (!features.controlnet_loader || !features.controlnet_apply_advanced) return { tone: 'warn', label: 'Nodes missing' };
      if (!controlnets.length) return { tone: 'warn', label: 'No models' };
      return { tone: 'ok', label: `${controlnets.length} available` };
    }
    if (key === 'advanced reference controls') {
      if (!features.ipadapter_ready) return { tone: 'warn', label: 'Nodes missing' };
      if (!ipModels.length || !clipVision.length) return { tone: 'warn', label: 'Models missing' };
      return { tone: 'ok', label: 'Ready' };
    }
    if (key === 'advanced raw mask override' || key === 'wildcards') {
      return { tone: 'purple', label: 'Power-user' };
    }
    if (key === 'character creator' || key === 'keyword snippets' || key === 'style add-ons' || key === 'prompt payload') {
      return { tone: 'info', label: 'Ready' };
    }
    return { tone: 'info', label: 'Ready' };
  }

  function updateSectionChips() {
    document.querySelectorAll(`${ROOT_SELECTOR} details.accordion-block, ${ROOT_SELECTOR} .generation-shell-card`).forEach(section => {
      const title = section.querySelector('.accordion-title')?.textContent || '';
      const row = section.querySelector('.neo-guide-chip-row');
      if (!title || !row) return;
      const state = resolveSectionState(title);
      const chip = baseCapabilityChip(row);
      chip.textContent = state.label;
      chip.className = `neo-guide-chip neo-capability-chip tone-${state.tone || 'info'}`;
    });
  }

  function buildBaseWarnings() {
    const rt = runtime();
    const session = rt?.getImageSession?.() || { connected: false };
    const catalog = rt?.getCatalogState?.() || {};
    const stats = rt?.getSystemStats?.() || {};
    const warnings = [];
    const mode = $('generation-workflow-type')?.value || 'txt2img';
    const sourceNeeded = mode !== 'txt2img';
    const checkpoint = String($('generation-checkpoint')?.value || '').trim();
    const width = numberValue('generation-width', 1024);
    const height = numberValue('generation-height', 1024);
    const megapixels = (width * height) / 1000000;
    const batchSize = numberValue('generation-batch-size', 1);
    const refineEnabled = boolFromSelect('generation-refine-enabled');
    const refineScale = numberValue('generation-refine-scale', 1.5);
    const supirEnabled = boolFromSelect('generation-supir-enabled');
    const supirScale = numberValue('generation-supir-scale', 1.5);
    const sourceSelected = hasFiles('generation-source-image');
    const maskSelected = hasFiles('generation-mask-image');
    const controlEnabled = !!$('generation-controlnet-enabled')?.checked;
    const controlModel = String($('generation-controlnet-name')?.value || '').trim();
    const controlImage = hasFiles('generation-control-image');
    const ipEnabled = !!$('generation-ipadapter-enabled')?.checked;
    const ipModel = String($('generation-ipadapter-name')?.value || '').trim();
    const ipClip = String($('generation-ipadapter-clip-vision')?.value || '').trim();
    const ipImage = hasFiles('generation-ipadapter-image');
    const devices = Array.isArray(stats.devices) ? stats.devices : [];
    const vramGB = devices.length && devices[0]?.vram_total ? Number(devices[0].vram_total) / (1024 * 1024 * 1024) : 0;

    if (!session.connected) {
      warnings.push({ tone: 'danger', text: 'No image backend is connected yet. Queueing is blocked until ComfyUI is attached.' });
      return warnings;
    }
    if (!Array.isArray(catalog.checkpoints) || !catalog.checkpoints.length) {
      warnings.push({ tone: 'warn', text: 'The backend is connected, but no checkpoints were found in the live catalog yet.' });
    }
    if (!checkpoint) {
      warnings.push({ tone: 'warn', text: 'No checkpoint is selected. Pick a model before you queue.' });
    }
    if (sourceNeeded && !sourceSelected) {
      warnings.push({ tone: 'warn', text: `${mode.toUpperCase()} needs a source image before the run will make sense.` });
    }
    if (mode === 'inpaint' && !maskSelected) {
      warnings.push({ tone: 'warn', text: 'Inpaint mode currently has no saved mask. Use Edit Mask or load a raw mask override first.' });
    }
    if (mode === 'outpaint') {
      const totalPad = numberValue('generation-outpaint-left', 0) + numberValue('generation-outpaint-right', 0) + numberValue('generation-outpaint-top', 0) + numberValue('generation-outpaint-bottom', 0);
      if (totalPad <= 0) warnings.push({ tone: 'warn', text: 'Outpaint mode is active but all padding values are still zero.' });
    }
    if (mode !== 'txt2img' && batchSize > 1) {
      warnings.push({ tone: 'info', text: 'Img2img, inpaint, and outpaint currently collapse to batch size 1 in the workflow adapter. Bigger batch values will not behave like normal batch runs.' });
    }
    if (controlEnabled && (!controlModel || !controlImage)) {
      warnings.push({ tone: 'warn', text: 'Primary ControlNet is enabled, but it is missing a model or control image.' });
    }
    if (ipEnabled && (!ipModel || !ipClip || !ipImage)) {
      warnings.push({ tone: 'warn', text: 'Primary IP-Adapter is enabled, but it is missing a reference image, model, or CLIP Vision encoder.' });
    }
    if (megapixels >= 1.8 && vramGB && vramGB < 10) {
      warnings.push({ tone: 'warn', text: `Current canvas is about ${megapixels.toFixed(2)} MP. On roughly ${vramGB.toFixed(1)} GB VRAM, that can get unstable fast.` });
    }
    if (refineEnabled && refineScale > 1.8 && vramGB && vramGB < 12) {
      warnings.push({ tone: 'warn', text: `Upscale Lab is set to ${refineScale.toFixed(2)}x. On this VRAM class, start closer to 1.5x until the base run is stable.` });
    }
    if (supirEnabled && (supirScale > 1.6 || (vramGB && vramGB < 12))) {
      warnings.push({ tone: 'danger', text: 'SUPIR is enabled. Treat it as a heavy late-stage pass, especially on lower VRAM setups.' });
    }
    return warnings;
  }

  function buildAuditWarnings() {
    const audit = runtime()?.getDependencyAuditState?.() || {};
    const issues = Array.isArray(audit.issues) ? audit.issues : [];
    const warnings = [];
    const summary = audit.summary || {};
    const recommendedPacks = Array.isArray(audit.recommended_packs) ? audit.recommended_packs : [];
    const missingPacks = recommendedPacks.filter(item => !item?.ready);

    if (missingPacks.length) {
      warnings.push({
        tone: 'info',
        title: 'Phase 1 core add-ons are not fully installed yet',
        text: missingPacks.map(item => `${item.label}${item.purpose ? ` — ${item.purpose}` : ''}`).join(' | '),
        code: missingPacks.map(item => `${item.label}: ${item.repo || 'repo not set'}`).join('\n'),
        codeLabel: 'Recommended node repos',
      });
    }

    if (summary.missing_nodes || summary.missing_models || summary.misplaced_models || summary.catalog_mismatches || summary.yaml_warnings) {
      const parts = [];
      if (summary.missing_nodes) parts.push(`${summary.missing_nodes} missing node${summary.missing_nodes === 1 ? '' : 's'}`);
      if (summary.missing_models) parts.push(`${summary.missing_models} missing model${summary.missing_models === 1 ? '' : 's'}`);
      if (summary.misplaced_models) parts.push(`${summary.misplaced_models} misplaced model${summary.misplaced_models === 1 ? '' : 's'}`);
      if (summary.catalog_mismatches) parts.push(`${summary.catalog_mismatches} backend mismatch${summary.catalog_mismatches === 1 ? '' : 'es'}`);
      if (summary.yaml_warnings) parts.push(`${summary.yaml_warnings} YAML warning${summary.yaml_warnings === 1 ? '' : 's'}`);
      warnings.push({
        tone: 'info',
        title: 'Dependency audit summary',
        text: parts.join(' · '),
      });
    }

    if (summary.yaml_active) {
      const fileCount = Array.isArray(audit.yaml?.files) ? audit.yaml.files.filter(item => item?.ok !== false).length : 0;
      warnings.push({
        tone: 'info',
        title: 'External model YAML detected',
        text: fileCount ? `${fileCount} extra model path file${fileCount === 1 ? '' : 's'} detected. The dependency audit is checking expected folders first, then YAML-mapped model roots.` : 'External model path mode looks active, so the audit will also check YAML-mapped model roots.',
      });
    }

    issues.forEach(issue => {
      if (issue.kind === 'node_manager_path_missing') {
        warnings.push({
          tone: 'warn',
          title: 'custom_nodes path is not verified yet',
          text: issue.message || 'Neo could not verify the local custom_nodes path yet.',
        });
        return;
      }
      if (issue.kind === 'yaml_file_error') {
        warnings.push({
          tone: 'warn',
          title: 'Model path YAML could not be read',
          text: `${issue.path || 'Unknown YAML file'}${issue.error ? ` | ${issue.error}` : ''}`,
        });
        return;
      }
      if (issue.kind === 'missing_node') {
        warnings.push({
          tone: 'danger',
          title: `${issue.feature_label || 'Feature'} is missing a custom node`,
          text: issue.message || `Missing node: ${issue.label || issue.node_name || 'Unknown node'}.`,
        });
        return;
      }
      if (issue.kind === 'model_found_elsewhere') {
        warnings.push({
          tone: 'warn',
          title: 'Model found in the wrong place',
          text: `${issue.feature_label || 'Feature'} needs ${issue.model_name || 'this model'} in ${issue.expected_dir || 'its expected folder'}, but Neo found it at ${issue.found_path || 'another path'}.`,
          code: issue.yaml_hint || '',
          codeLabel: issue.yaml_hint ? 'Suggested YAML entry' : '',
        });
        return;
      }
      if (issue.kind === 'backend_catalog_mismatch') {
        warnings.push({
          tone: 'info',
          title: 'Backend catalog did not expose a local model yet',
          text: `${issue.model_name || 'Model'} exists at ${issue.resolved_path || 'a local path'}, but ComfyUI did not list it in the live catalog yet. Refresh or restart the backend after checking the folder rules.`,
        });
        return;
      }
      if (issue.kind === 'missing_model') {
        const extra = [];
        if (issue.expected_dir) extra.push(`Expected folder: ${issue.expected_dir}`);
        if (Array.isArray(issue.yaml_paths) && issue.yaml_paths.length) extra.push(`Mapped YAML folders: ${issue.yaml_paths.join(' · ')}`);
        warnings.push({
          tone: 'warn',
          title: `${issue.feature_label || 'Feature'} is missing a model`,
          text: `${issue.model_name || 'Unknown model'} is missing for ${issue.category_label || issue.category || 'this section'}. ${extra.join(' | ')}`.trim(),
          code: issue.yaml_hint || '',
          codeLabel: issue.yaml_hint ? 'YAML hint' : '',
        });
        return;
      }
      if (issue.kind === 'yaml_mapping_missing') {
        warnings.push({
          tone: 'info',
          title: 'YAML mapping looks incomplete',
          text: issue.message || `${issue.model_name || 'Model'} may exist, but Neo could not resolve it from the mapped YAML paths.`,
          code: issue.yaml_hint || '',
          codeLabel: issue.yaml_hint ? 'Suggested entry' : '',
        });
      }
    });
    return warnings;
  }

  function buildWarnings() {
    const warnings = [...buildAuditWarnings(), ...buildBaseWarnings()];
    if (!warnings.length) {
      warnings.push({ tone: 'ok', text: 'No major setup issues detected right now. This workspace looks safe to test.' });
    }
    return warnings;
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderWarnings() {
    const host = $('generation-ux-warning-list');
    if (!host) return;
    const warnings = buildWarnings();
    host.innerHTML = warnings.map(item => `
      <div class="neo-warning-item tone-${item.tone || 'info'}">
        <span class="neo-warning-dot"></span>
        <div class="neo-warning-copy">
          ${item.title ? `<div class="neo-warning-copy-title">${escapeHtml(item.title)}</div>` : ''}
          <div>${escapeHtml(item.text || '')}</div>
          ${item.code ? `<div class="neo-warning-code-label">${escapeHtml(item.codeLabel || 'Fix hint')}</div><pre class="neo-warning-code">${escapeHtml(item.code)}</pre>` : ''}
        </div>
      </div>`).join('');
  }

  function bindFieldRefreshes() {
    const ids = [
      'generation-workflow-type','generation-checkpoint','generation-width','generation-height','generation-batch-size',
      'generation-source-image','generation-mask-image','generation-refine-enabled','generation-refine-scale','generation-refine-mode','generation-refine-upscaler',
      'generation-supir-enabled','generation-supir-scale','generation-supir-model','generation-supir-sdxl-model','generation-outpaint-left','generation-outpaint-right',
      'generation-outpaint-top','generation-outpaint-bottom','generation-controlnet-enabled','generation-controlnet-name',
      'generation-control-image','generation-ipadapter-enabled','generation-ipadapter-name','generation-ipadapter-clip-vision',
      'generation-ipadapter-image','generation-detailer-enabled','generation-detailer-detector-type','generation-detailer-model','generation-detailer-sam-model'
    ];
    ids.forEach(id => {
      const el = $(id);
      if (!el || el.dataset.neoReliabilityBound === '1') return;
      const handler = () => {
        queueRefresh();
        queueAuditRefresh();
      };
      el.addEventListener('change', handler);
      el.addEventListener('input', handler);
      el.dataset.neoReliabilityBound = '1';
    });
  }

  let refreshTimer = 0;
  let auditRefreshTimer = 0;
  function queueRefresh() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(refreshAll, 40);
  }

  function queueAuditRefresh() {
    window.clearTimeout(auditRefreshTimer);
    auditRefreshTimer = window.setTimeout(() => runtime()?.refreshDependencyAudit?.({ silent:true }), 500);
  }

  function refreshAll() {
    createWarningPanel();
    updateSectionChips();
    renderWarnings();
    bindFieldRefreshes();
  }

  function init() {
    createWarningPanel();
    refreshAll();
    runtime()?.refreshDependencyAudit?.({ silent:true }).catch?.(() => {});
    window.addEventListener('neo:generation-catalog-refreshed', () => {
      refreshAll();
      queueAuditRefresh();
    });
    window.addEventListener('neo:generation-detailer-models-refreshed', () => {
      refreshAll();
      queueAuditRefresh();
    });
    window.addEventListener('neo:generation-dependency-audit-refreshed', refreshAll);
    document.addEventListener('change', event => {
      if (event.target && event.target.closest(ROOT_SELECTOR)) queueRefresh();
    });
    const root = document.querySelector(ROOT_SELECTOR);
    if (root) {
      const observer = new MutationObserver(queueRefresh);
      observer.observe(root, { childList: true, subtree: true });
    }
  }

  ready(init);
})();
