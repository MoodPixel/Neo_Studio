(function () {
  const ROOT_SELECTOR = '#tab-generate';
  const compareState = {
    items: [],
    winnerId: '',
    pollTimer: null,
  };
  const inspectorState = {
    output: null,
    job: null,
    draft: null,
    source: 'runtime',
  };

  const axisDefinitions = {
    seed: {
      label: 'Seed',
      placeholder: '1001, 2002, 3003',
      help: 'Best when you want the same prompt and settings, but want to see different image outcomes.'
    },
    cfg: {
      label: 'CFG',
      placeholder: '4.5, 5.5, 6.5',
      help: 'Useful for testing how hard the prompt should push the image.'
    },
    steps: {
      label: 'Steps',
      placeholder: '20, 28, 36',
      help: 'Great for checking where extra render time stops helping.'
    },
    sampler: {
      label: 'Sampler',
      placeholder: 'euler, dpmpp_2m, dpmpp_sde',
      help: 'Use this to compare the feel and texture of the same prompt across samplers.'
    },
    dt_preset: {
      label: 'CFG Fix preset',
      placeholder: 'off, safe, detail_push, aggressive, smart_auto',
      help: 'Compare Dynamic Thresholding presets while keeping the same prompt, seed, CFG, sampler, and size.'
    },
    dt_mimic: {
      label: 'CFG Fix mimic',
      placeholder: '5, 6, 7, 8',
      help: 'Compare custom Mimic CFG values. Neo keeps the current CFG Fix preset on, enables Customize values, and changes only Mimic CFG.'
    },
    dt_percentile: {
      label: 'CFG Fix percentile',
      placeholder: '1.0, 0.99, 0.98',
      help: 'Compare custom Dynamic Thresholding percentile values. Lower values usually control highlight burn harder but can flatten contrast.'
    },
    dt_combo: {
      label: 'CFG Fix combo',
      placeholder: 'off, simple:7:0.99, simple:6:0.98, full:7:0.99',
      help: 'Power-user axis. Use off or mode:mimic:percentile, for example simple:7:0.99.'
    },
    lora_strength: {
      label: 'LoRA strength',
      placeholder: '0.6, 0.8, 1.0',
      help: 'Only useful when you already have at least one LoRA in the workflow stack.'
    },
    control_strength: {
      label: 'ControlNet strength',
      placeholder: '0.5, 0.8, 1.0',
      help: 'Use this to see how tightly the guide image should control the result.'
    },
    ip_weight: {
      label: 'IP-Adapter weight',
      placeholder: '0.5, 0.8, 1.0',
      help: 'Good for tuning identity or reference pull without crushing the base prompt.'
    },
  };

  const dynamicThresholdingPresetDefaults = {
    off: { enabled: false, preset: 'off', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 1.0, custom_values: false },
    safe: { enabled: true, preset: 'safe', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 1.0, custom_values: false },
    detail_push: { enabled: true, preset: 'detail_push', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 0.99, custom_values: false },
    aggressive: { enabled: true, preset: 'aggressive', mode: 'simple', mimic_scale: 6.0, threshold_percentile: 0.98, custom_values: false },
    smart_auto: { enabled: true, preset: 'smart_auto', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 0.99, custom_values: false },
    advanced: { enabled: true, preset: 'advanced', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 0.99, custom_values: true },
  };

  function normalizeDynamicThresholding(value) {
    const row = value && typeof value === 'object' ? value : {};
    const preset = String(row.preset || (row.enabled ? 'advanced' : 'off')).trim() || 'off';
    const base = dynamicThresholdingPresetDefaults[preset] || dynamicThresholdingPresetDefaults.off;
    const mode = String(row.mode || base.mode || 'simple').toLowerCase() === 'full' ? 'full' : 'simple';
    const mimic = Number(row.mimic_scale ?? base.mimic_scale ?? 7.0);
    const percentile = Number(row.threshold_percentile ?? base.threshold_percentile ?? 1.0);
    return {
      ...base,
      ...row,
      preset,
      enabled: preset !== 'off' && row.enabled !== false,
      mode,
      node: mode === 'full' ? 'DynamicThresholdingFull' : 'DynamicThresholdingSimple',
      mimic_scale: Math.max(1, Math.min(30, Number.isFinite(mimic) ? mimic : 7.0)),
      threshold_percentile: Math.max(0.80, Math.min(1.00, Number.isFinite(percentile) ? percentile : 1.0)),
      auto_disable_low_cfg: true,
      auto_disable_family: true,
    };
  }

  function isDynamicThresholdingAxis(axis) {
    return ['dt_preset', 'dt_mimic', 'dt_percentile', 'dt_combo'].includes(axis);
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) { return document.getElementById(id); }

  function runtime() { return window.NeoStudioApp?.generation?.getRuntime?.() || window.NeoGenerationRuntime || null; }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function deepClone(value) {
    try { return JSON.parse(JSON.stringify(value)); }
    catch (_) { return value; }
  }

  function formatMaybeNumber(value) {
    if (value === '' || value == null) return '';
    const num = Number(value);
    if (Number.isFinite(num)) {
      if (Number.isInteger(num)) return String(num);
      return String(Math.round(num * 1000) / 1000).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
    }
    return String(value);
  }

  function basename(path) {
    const raw = String(path || '').trim();
    if (!raw) return '';
    return raw.split(/[\\/]/).pop() || raw;
  }

  function getAxisDefinition(axis) {
    return axisDefinitions[axis] || axisDefinitions.cfg;
  }

  function compareStatusTone(state) {
    const key = String(state || '').toLowerCase();
    if (['completed', 'captured', 'winner'].includes(key)) return 'tone-ok';
    if (['error', 'failed'].includes(key)) return 'tone-danger';
    if (['cancelled', 'warn'].includes(key)) return 'tone-warn';
    return 'tone-info';
  }

  function isTerminalState(state) {
    const key = String(state || '').toLowerCase();
    return ['completed', 'error', 'cancelled', 'captured'].includes(key);
  }

  function createPowerPanel() {
    const helperHost = $('generation-helper-tab-host');
    const helperPanel = $('generation-helper-status')?.closest('.workspace-helper-panel');
    const smartPanel = $('generation-smart-panel');
    const warningPanel = $('generation-ux-warning-panel');
    const foundation = $('generation-ux-foundation-bar');
    const anchor = helperHost || smartPanel || warningPanel || foundation;
    if (!anchor || $('generation-power-panel')) return;
    const html = `
      <div class="neo-smart-panel neo-power-panel" id="generation-power-panel" style="margin-top:14px;">
        <div class="neo-power-grid">
          <div class="neo-smart-card" id="generation-compare-lab-card">
            <div class="neo-smart-card-header">
              <div>
                <div class="neo-smart-title">Power Compare helper</div>
                <div class="neo-smart-subtitle">Batch-test helper axes like CFG Fix presets, mimic, percentile, sampler, seed, and settings without manually rebuilding the workspace.</div>
              </div>
              <div class="neo-smart-actions">
                <button class="btn btn-small" id="btn-generation-compare-run" type="button">Queue compare set</button>
                <button class="btn btn-small" id="btn-generation-compare-capture" type="button">Capture current output</button>
                <button class="btn btn-small" id="btn-generation-compare-clear" type="button">Clear session</button>
              </div>
            </div>
            <div class="neo-smart-card-body">
              <div class="grid grid-2">
                <div>
                  <label for="generation-compare-axis">Compare axis</label>
                  <select id="generation-compare-axis">
                    ${Object.entries(axisDefinitions).map(([key, meta]) => `<option value="${escapeHtml(key)}">${escapeHtml(meta.label)}</option>`).join('')}
                  </select>
                </div>
                <div>
                  <label for="generation-compare-values">Values</label>
                  <textarea id="generation-compare-values" rows="3" placeholder="${escapeHtml(getAxisDefinition('cfg').placeholder)}"></textarea>
                </div>
              </div>
              <div class="neo-compare-note" id="generation-compare-help" style="margin-top:10px;">${escapeHtml(getAxisDefinition('cfg').help)}</div>
              <div class="neo-compare-note" style="margin-top:10px;">Neo queues each variant from the current workspace, restores your original settings after the run is staged, then tracks each queued job inside this compare session.</div>
              <div class="neo-compare-note" style="margin-top:8px;">Tip: for Dynamic Thresholding, use <b>CFG Fix preset</b> for quick tests or <b>CFG Fix combo</b> with values like <code>off, simple:7:0.99, simple:6:0.98</code>.</div>
              <div id="generation-compare-status" class="neo-recipe-note" style="margin-top:12px;">Set one axis, add comma-separated values, and Neo will do the repetitive part for you.</div>
            </div>
          </div>
          <div class="neo-smart-card" id="generation-compare-session-card">
            <div class="neo-smart-card-header">
              <div>
                <div class="neo-smart-title">Compare session</div>
                <div class="neo-smart-subtitle">Keep your queued variants, manual captures, and winner picks in one place.</div>
              </div>
            </div>
            <div id="generation-compare-list" class="neo-smart-card-body neo-compare-list"></div>
          </div>
        </div>
      </div>
    `;
    if (helperHost) {
      if (helperPanel && helperPanel.parentElement === helperHost) helperPanel.insertAdjacentHTML('afterend', html);
      else helperHost.insertAdjacentHTML('beforeend', html);
      return;
    }
    anchor.insertAdjacentHTML('afterend', html);
  }


  function createOutputInspector() {
    const host = $('generation-output-inspector-host');
    if (!host || $('generation-output-inspector-panel')) return;
    const panel = document.createElement('div');
    panel.id = 'generation-output-inspector-panel';
    panel.className = 'neo-smart-card neo-output-inspector-panel';
    host.prepend(panel);
  }

  function updateCompareAxisUI() {
    const axis = $('generation-compare-axis')?.value || 'cfg';
    const meta = getAxisDefinition(axis);
    if ($('generation-compare-values')) $('generation-compare-values').placeholder = meta.placeholder;
    if ($('generation-compare-help')) $('generation-compare-help').textContent = meta.help;
  }

  function setCompareStatus(message, tone = 'info') {
    const el = $('generation-compare-status');
    if (!el) return;
    el.className = `neo-recipe-note ${tone === 'success' ? 'tone-success' : tone === 'warn' ? 'tone-warn' : tone === 'error' ? 'tone-error' : ''}`.trim();
    el.textContent = message;
  }

  function parseCompareValues(raw, axis) {
    const parts = String(raw || '')
      .split(/[\n,|]/g)
      .map(item => String(item || '').trim())
      .filter(Boolean);
    const seen = new Set();
    const out = [];
    parts.forEach(item => {
      const normalized = ['sampler', 'dt_preset', 'dt_combo'].includes(axis) ? item : formatMaybeNumber(item);
      const key = String(normalized || '').toLowerCase();
      if (!normalized || seen.has(key)) return;
      seen.add(key);
      out.push(normalized);
    });
    return out;
  }

  function draftSupportsAxis(draft, axis) {
    if (!draft || typeof draft !== 'object') return false;
    if (axis === 'lora_strength') return !!((Array.isArray(draft.loras) && draft.loras.length) || draft.lora_name);
    if (axis === 'control_strength') return !!((Array.isArray(draft.controlnet_units) && draft.controlnet_units.length) || draft.controlnet_name);
    if (axis === 'ip_weight') return !!((Array.isArray(draft.ipadapter_units) && draft.ipadapter_units.length) || draft.ipadapter_name || draft.ipadapter_clip_vision);
    if (isDynamicThresholdingAxis(axis)) {
      const family = String(draft.family || draft.model_family || draft.workflow_family || 'sdxl_sd').toLowerCase();
      return !family || ['sdxl_sd', 'sdxl', 'sd'].includes(family);
    }
    return true;
  }

  function applyDynamicThresholdingAxisToDraft(draft, axis, rawValue) {
    const value = String(rawValue || '').trim();
    const current = normalizeDynamicThresholding(draft.dynamic_thresholding);
    if (axis === 'dt_preset') {
      const key = value.toLowerCase().replace(/[\s-]+/g, '_');
      const preset = dynamicThresholdingPresetDefaults[key] ? key : 'off';
      draft.dynamic_thresholding = normalizeDynamicThresholding(dynamicThresholdingPresetDefaults[preset]);
      return draft;
    }
    if (axis === 'dt_combo') {
      if (value.toLowerCase() === 'off') {
        draft.dynamic_thresholding = normalizeDynamicThresholding(dynamicThresholdingPresetDefaults.off);
        return draft;
      }
      const parts = value.split(':').map(part => part.trim()).filter(Boolean);
      const mode = String(parts[0] || current.mode || 'simple').toLowerCase() === 'full' ? 'full' : 'simple';
      const mimic = Number(parts[1] ?? current.mimic_scale ?? 7.0);
      const percentile = Number(parts[2] ?? current.threshold_percentile ?? 0.99);
      draft.dynamic_thresholding = normalizeDynamicThresholding({
        ...current,
        enabled: true,
        preset: 'advanced',
        mode,
        mimic_scale: Number.isFinite(mimic) ? mimic : current.mimic_scale,
        threshold_percentile: Number.isFinite(percentile) ? percentile : current.threshold_percentile,
        custom_values: true,
      });
      return draft;
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return draft;
    if (axis === 'dt_mimic') {
      draft.dynamic_thresholding = normalizeDynamicThresholding({
        ...current,
        enabled: true,
        preset: current.preset === 'off' ? 'advanced' : current.preset,
        mimic_scale: numeric,
        custom_values: true,
      });
      return draft;
    }
    if (axis === 'dt_percentile') {
      draft.dynamic_thresholding = normalizeDynamicThresholding({
        ...current,
        enabled: true,
        preset: current.preset === 'off' ? 'advanced' : current.preset,
        threshold_percentile: numeric,
        custom_values: true,
      });
      return draft;
    }
    return draft;
  }

  function applyAxisToDraft(draft, axis, rawValue) {
    const value = String(rawValue || '').trim();
    if (!draft || !value) return draft;
    if (axis === 'sampler') {
      draft.sampler = value;
      return draft;
    }
    if (isDynamicThresholdingAxis(axis)) return applyDynamicThresholdingAxisToDraft(draft, axis, value);
    const numeric = Number(value);
    if (axis !== 'sampler' && !Number.isFinite(numeric)) return draft;
    switch (axis) {
      case 'seed':
        draft.seed = formatMaybeNumber(numeric);
        break;
      case 'cfg':
        draft.cfg = formatMaybeNumber(numeric);
        break;
      case 'steps':
        draft.steps = formatMaybeNumber(Math.round(numeric));
        break;
      case 'lora_strength':
        draft.lora_strength = formatMaybeNumber(numeric);
        if (Array.isArray(draft.loras) && draft.loras.length) draft.loras[0].strength = numeric;
        break;
      case 'control_strength':
        draft.controlnet_strength = formatMaybeNumber(numeric);
        if (Array.isArray(draft.controlnet_units) && draft.controlnet_units.length) draft.controlnet_units[0].strength = numeric;
        break;
      case 'ip_weight':
        draft.ipadapter_weight = formatMaybeNumber(numeric);
        if (Array.isArray(draft.ipadapter_units) && draft.ipadapter_units.length) draft.ipadapter_units[0].weight = numeric;
        break;
      default:
        break;
    }
    return draft;
  }

  function payloadToDraft(payload) {
    const detailerBase = payload?.detailer || {};
    const detailerPasses = Array.isArray(payload?.detailer_passes) ? payload.detailer_passes : [];
    const detailerPrimary = detailerPasses[0] || detailerBase || {};
    const controlnetUnits = Array.isArray(payload?.controlnet_units) ? payload.controlnet_units.map(item => ({ ...item })) : [];
    const ipadapterUnits = Array.isArray(payload?.ipadapter_units) ? payload.ipadapter_units.map(item => ({ ...item })) : [];
    const loras = Array.isArray(payload?.loras) ? payload.loras.map(item => ({ ...item })) : [];
    return {
      version: 5,
      updated_at: Date.now(),
      workflow_type: String(payload?.mode || payload?.workflow_type || 'txt2img'),
      family: String(payload?.family || payload?.model_family || 'sdxl_sd'),
      dynamic_thresholding: normalizeDynamicThresholding(payload?.dynamic_thresholding),
      checkpoint: String(payload?.checkpoint || ''),
      vae: String(payload?.vae || ''),
      sampler: String(payload?.sampler || 'euler'),
      scheduler: String(payload?.scheduler || 'normal'),
      width: formatMaybeNumber(payload?.width || 1024),
      height: formatMaybeNumber(payload?.height || 1024),
      size_preset: 'custom',
      steps: formatMaybeNumber(payload?.steps || 28),
      batch_size: formatMaybeNumber(payload?.batch_size || 1),
      cfg: formatMaybeNumber(payload?.cfg || 5.2),
      denoise: formatMaybeNumber(payload?.denoise ?? 1.0),
      seed: String(payload?.seed ?? '-1'),
      positive: String(payload?.positive || ''),
      negative: String(payload?.negative || ''),
      selected_style: '',
      style_enabled: payload?.style_enabled !== false,
      active_styles: [],
      style_name: '',
      style_positive: String(payload?.style_positive || ''),
      style_negative: String(payload?.style_negative || ''),
      source_resize_mode: String(payload?.source_resize_mode || 'native'),
      inpaint_target: String(payload?.inpaint_target || 'masked'),
      inpaint_context: String(payload?.inpaint_context || 'full_image'),
      grow_mask_by: formatMaybeNumber(payload?.grow_mask_by || 6),
      mask_feather: formatMaybeNumber(payload?.mask_feather || 0),
      outpaint_left: formatMaybeNumber(payload?.outpaint_left || 0),
      outpaint_top: formatMaybeNumber(payload?.outpaint_top || 0),
      outpaint_right: formatMaybeNumber(payload?.outpaint_right || 0),
      outpaint_bottom: formatMaybeNumber(payload?.outpaint_bottom || 0),
      outpaint_feather: formatMaybeNumber(payload?.outpaint_feather || 24),
      outpaint_preset: 'custom',
      outpaint_anchor: 'center',
      detailer_enabled: !!(detailerPrimary?.enabled || detailerPasses.length),
      detailer_provider: String(detailerPrimary?.provider || 'ultralytics'),
      detailer_mode: String(detailerPrimary?.mode || 'face'),
      detailer_detector_type: String(detailerPrimary?.detector_type || 'bbox'),
      detailer_model: String(detailerPrimary?.detector_model || detailerPrimary?.model || ''),
      detailer_sam_model: String(detailerPrimary?.sam_model || ''),
      detailer_custom_classes: String(detailerPrimary?.custom_classes || ''),
      detailer_confidence: formatMaybeNumber(detailerPrimary?.confidence ?? 0.35),
      detailer_topk: formatMaybeNumber(detailerPrimary?.top_k ?? detailerPrimary?.topk ?? 0),
      detailer_bbox_grow: formatMaybeNumber(detailerPrimary?.bbox_grow ?? 12),
      detailer_mask_blur: formatMaybeNumber(detailerPrimary?.mask_blur ?? 4),
      detailer_denoise: formatMaybeNumber(detailerPrimary?.denoise ?? 0.12),
      detailer_steps: formatMaybeNumber(detailerPrimary?.steps ?? 12),
      detailer_use_main_prompt: detailerPrimary?.use_main_prompt !== false,
      detailer_force_inpaint: detailerPrimary?.force_inpaint !== false,
      detailer_positive: String(detailerPrimary?.positive || ''),
      detailer_negative: String(detailerPrimary?.negative || ''),
      detailer_custom_detector_root: String(payload?.detailer_custom_detector_root || ''),
      detailer_custom_sam_root: String(payload?.detailer_custom_sam_root || ''),
      detailer_sam_preset: String(payload?.detailer_sam_preset || ''),
      detailer_passes: detailerPasses.map(item => ({ ...item })),
      lora_enabled: !!(loras.length || payload?.lora_name),
      lora_name: String(payload?.lora_name || loras[0]?.name || ''),
      lora_strength: formatMaybeNumber(payload?.lora_strength ?? loras[0]?.strength ?? 0.8),
      loras,
      controlnet_enabled: !!(controlnetUnits.length || payload?.controlnet_name),
      controlnet_unit: String(controlnetUnits[0]?.unit || payload?.controlnet_unit || 'auto'),
      controlnet_name: String(payload?.controlnet_name || controlnetUnits[0]?.model || ''),
      controlnet_preprocessor: String(payload?.controlnet_preprocessor || controlnetUnits[0]?.preprocessor || 'none'),
      controlnet_strength: formatMaybeNumber(payload?.controlnet_strength ?? controlnetUnits[0]?.strength ?? 1.0),
      controlnet_units: controlnetUnits,
      ipadapter_enabled: !!(ipadapterUnits.length || payload?.ipadapter_name || payload?.ipadapter_clip_vision),
      ipadapter_mode: String(payload?.ipadapter_mode || ipadapterUnits[0]?.mode || 'standard'),
      ipadapter_name: String(payload?.ipadapter_name || ipadapterUnits[0]?.model || ''),
      ipadapter_clip_vision: String(payload?.ipadapter_clip_vision || ipadapterUnits[0]?.clip_vision || ''),
      ipadapter_faceid_preset: String(payload?.ipadapter_faceid_preset || ipadapterUnits[0]?.faceid_preset || 'FACEID PLUS V2'),
      ipadapter_faceid_provider: String(payload?.ipadapter_faceid_provider || ipadapterUnits[0]?.faceid_provider || 'CUDA'),
      ipadapter_faceid_lora_strength: formatMaybeNumber(payload?.ipadapter_faceid_lora_strength ?? ipadapterUnits[0]?.faceid_lora_strength ?? 0.75),
      ipadapter_weight: formatMaybeNumber(payload?.ipadapter_weight ?? ipadapterUnits[0]?.weight ?? 1.0),
      ipadapter_weight_faceidv2: formatMaybeNumber(payload?.ipadapter_weight_faceidv2 ?? ipadapterUnits[0]?.weight_faceidv2 ?? 1.0),
      ipadapter_weight_type: String(payload?.ipadapter_weight_type || ipadapterUnits[0]?.weight_type || 'linear'),
      ipadapter_combine_embeds: String(payload?.ipadapter_combine_embeds || ipadapterUnits[0]?.combine_embeds || 'concat'),
      ipadapter_embeds_scaling: String(payload?.ipadapter_embeds_scaling || ipadapterUnits[0]?.embeds_scaling || 'V only'),
      ipadapter_start_at: formatMaybeNumber(payload?.ipadapter_start_at ?? ipadapterUnits[0]?.start_at ?? 0),
      ipadapter_end_at: formatMaybeNumber(payload?.ipadapter_end_at ?? ipadapterUnits[0]?.end_at ?? 1),
      ipadapter_units: ipadapterUnits,
      refine_enabled: String(!!payload?.refine_enabled),
      refine_mode: String(payload?.refine_mode || 'latent'),
      refine_resize_method: String(payload?.refine_resize_method || 'lanczos'),
      refine_upscaler: String(payload?.refine_upscaler || ''),
      refine_scale: formatMaybeNumber(payload?.refine_scale ?? 1.5),
      refine_steps: formatMaybeNumber(payload?.refine_steps ?? 12),
      refine_denoise: formatMaybeNumber(payload?.refine_denoise ?? 0.12),
      refine_cfg: formatMaybeNumber(payload?.refine_cfg ?? payload?.cfg ?? 5.2),
      refine_sampler: String(payload?.refine_sampler || ''),
      refine_scheduler: String(payload?.refine_scheduler || ''),
      refine_tiled_vae: String(payload?.refine_tiled_vae !== false),
      refine_tile_size: formatMaybeNumber(payload?.refine_tile_size ?? 512),
      refine_tile_overlap: formatMaybeNumber(payload?.refine_tile_overlap ?? 64),
      supir_enabled: String(!!payload?.supir_enabled),
      supir_model: String(payload?.supir_model || ''),
      supir_sdxl_model: String(payload?.supir_sdxl_model || ''),
      supir_scale: formatMaybeNumber(payload?.supir_scale ?? 1.5),
      supir_steps: formatMaybeNumber(payload?.supir_steps ?? 45),
      supir_restoration_scale: formatMaybeNumber(payload?.supir_restoration_scale ?? -1),
      supir_cfg_scale: formatMaybeNumber(payload?.supir_cfg_scale ?? 4.0),
      supir_control_scale: formatMaybeNumber(payload?.supir_control_scale ?? 1.0),
      supir_color_fix_type: String(payload?.supir_color_fix_type || 'Wavelet'),
      supir_tiled_vae: String(payload?.supir_tiled_vae !== false),
      supir_encoder_tile_size: formatMaybeNumber(payload?.supir_encoder_tile_size ?? 512),
      supir_decoder_tile_size: formatMaybeNumber(payload?.supir_decoder_tile_size ?? 64),
      supir_a_prompt: String(payload?.supir_a_prompt || 'high quality, detailed'),
      supir_n_prompt: String(payload?.supir_n_prompt || 'bad quality, blurry, messy'),
      output_root: String(payload?.output_root || ''),
      output_category: String(payload?.output_category || 'Uncategorized'),
      wildcard_root: String(payload?.wildcard_root || ''),
      wildcard_enabled: payload?.wildcard_enabled !== false,
      wildcard_selected_file: '',
      wildcard_target: 'positive',
      wildcard_auto_resolve: true,
      wildcard_use_seed: false,
      wildcard_preview_count: '3',
      wildcard_queue_count: '3',
      notes: String(payload?.notes || ''),
    };
  }

  function getContextDraft() {
    if (inspectorState.draft) return deepClone(inspectorState.draft);
    if (inspectorState.job?.payload) return payloadToDraft(inspectorState.job.payload);
    const rt = runtime();
    return rt?.getCurrentDraft ? deepClone(rt.getCurrentDraft()) : null;
  }

  function setInspectorContext(output, job, draft = null, source = 'runtime') {
    inspectorState.output = output || null;
    inspectorState.job = job || null;
    inspectorState.draft = draft ? deepClone(draft) : (job?.payload ? payloadToDraft(job.payload) : null);
    inspectorState.source = source;
    renderOutputInspector();
  }

  function syncInspectorFromRuntime() {
    const rt = runtime();
    if (!rt) return;
    const output = rt.getSelectedOutput ? rt.getSelectedOutput() : null;
    const job = rt.getLatestJob ? rt.getLatestJob() : null;
    if (output || job) setInspectorContext(output || (job?.outputs?.[0] || null), job, job?.payload ? payloadToDraft(job.payload) : null, 'runtime');
  }

  async function fetchJobLite(jobId) {
    const res = await fetch(`/api/generation/job/${encodeURIComponent(jobId)}?_=${Date.now()}`, { cache: 'no-store' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    return data.job || null;
  }

  function startComparePolling() {
    if (compareState.pollTimer) return;
    compareState.pollTimer = window.setInterval(async () => {
      const pending = compareState.items.filter(item => item.jobId && !isTerminalState(item.state));
      if (!pending.length) {
        stopComparePolling();
        return;
      }
      for (const item of pending) {
        try {
          const job = await fetchJobLite(item.jobId);
          if (!job) continue;
          item.state = String(job.state || item.state || 'queued');
          item.job = job;
          item.outputs = Array.isArray(job.outputs) ? job.outputs.slice() : [];
          item.output = item.outputs[0] || item.output || null;
          if (job.payload) item.draft = payloadToDraft(job.payload);
        } catch (err) {
          item.error = err?.message || 'Could not refresh this compare job.';
        }
      }
      renderCompareSession();
    }, 3500);
  }

  function stopComparePolling() {
    if (compareState.pollTimer) {
      window.clearInterval(compareState.pollTimer);
      compareState.pollTimer = null;
    }
  }

  async function queueCompareSet() {
    const rt = runtime();
    const queueGeneration = window.NeoStudioApp?.generation?.actions?.queueShell || window.queueGenerationShell;
    if (!rt?.getCurrentDraft || !rt?.applyDraft || !queueGeneration) {
      setCompareStatus('Neo compare tools are not ready yet. Refresh the page once and try again.', 'error');
      return;
    }
    const axis = $('generation-compare-axis')?.value || 'cfg';
    const values = parseCompareValues($('generation-compare-values')?.value || '', axis);
    const baseDraft = deepClone(rt.getCurrentDraft());
    if (!values.length) {
      setCompareStatus('Add at least two values so Neo has something real to compare.', 'warn');
      return;
    }
    if (!draftSupportsAxis(baseDraft, axis)) {
      const label = getAxisDefinition(axis).label;
      setCompareStatus(`${label} compare needs that feature to already exist in the workspace first.`, 'warn');
      return;
    }

    const btn = $('btn-generation-compare-run');
    const prev = btn?.textContent || 'Queue compare set';
    if (btn) {
      btn.setAttribute('disabled', 'disabled');
      btn.textContent = 'Queueing…';
    }
    let queued = 0;
    const created = [];
    try {
      for (const value of values) {
        const variantDraft = deepClone(baseDraft);
        applyAxisToDraft(variantDraft, axis, value);
        rt.applyDraft(variantDraft);
        const job = await queueGeneration({ watch: false, suppressSuccessStatus: true });
        if (!job?.id) continue;
        queued += 1;
        created.unshift({
          id: `cmp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          label: `${getAxisDefinition(axis).label}: ${value}`,
          axis,
          value,
          state: String(job.state || 'queued'),
          jobId: job.id,
          promptId: job.prompt_id || '',
          job,
          draft: deepClone(variantDraft),
          outputs: Array.isArray(job.outputs) ? job.outputs.slice() : [],
          output: Array.isArray(job.outputs) && job.outputs.length ? job.outputs[0] : null,
          createdAt: Date.now(),
        });
      }
      compareState.items = [...created, ...compareState.items].slice(0, 24);
      renderCompareSession();
      if (queued) {
        startComparePolling();
        setCompareStatus(`Queued ${queued} compare variant${queued === 1 ? '' : 's'}. Neo restored your base workspace after staging them.`, 'success');
      } else {
        setCompareStatus('Neo could not queue the compare set. Check the main Generation status for the exact failure.', 'error');
      }
    } catch (err) {
      setCompareStatus(err?.message || 'Could not queue the compare set.', 'error');
    } finally {
      rt.applyDraft(baseDraft);
      if (btn) {
        btn.removeAttribute('disabled');
        btn.textContent = prev;
      }
    }
  }

  function captureCurrentOutput() {
    const output = inspectorState.output || runtime()?.getSelectedOutput?.() || null;
    const job = inspectorState.job || runtime()?.getLatestJob?.() || null;
    const draft = inspectorState.draft || (job?.payload ? payloadToDraft(job.payload) : null);
    if (!output) {
      setCompareStatus('Pick a generated image first, then capture it into the compare session.', 'warn');
      return;
    }
    compareState.items.unshift({
      id: `cap_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      label: `Captured · ${basename(output.saved_filename || output.filename || 'output')}`,
      axis: 'captured',
      value: '',
      state: 'captured',
      jobId: job?.id || '',
      promptId: job?.prompt_id || '',
      job: job || null,
      draft: draft ? deepClone(draft) : null,
      outputs: [output],
      output,
      createdAt: Date.now(),
    });
    compareState.items = compareState.items.slice(0, 24);
    renderCompareSession();
    setCompareStatus('Current output captured into the compare session.', 'success');
  }

  function removeCompareItem(id) {
    compareState.items = compareState.items.filter(item => item.id !== id);
    if (compareState.winnerId === id) compareState.winnerId = '';
    renderCompareSession();
    if (!compareState.items.length) stopComparePolling();
  }

  function markCompareWinner(id) {
    compareState.winnerId = compareState.winnerId === id ? '' : id;
    renderCompareSession();
  }

  function previewCompareItem(id) {
    const item = compareState.items.find(entry => entry.id === id);
    if (!item?.output?.view_url) {
      setCompareStatus('That compare item does not have a rendered image yet.', 'warn');
      return;
    }
    const rt = runtime();
    if (rt?.activateOutput) rt.activateOutput({ ...item.output }, { label: item.label || 'Compare preview' });
    setInspectorContext(item.output, item.job, item.draft, 'compare');
  }

  function applyCompareItemToShell(id) {
    const item = compareState.items.find(entry => entry.id === id);
    const draft = item?.draft || (item?.job?.payload ? payloadToDraft(item.job.payload) : null);
    if (!item || !draft) {
      setCompareStatus('Neo could not rebuild that compare item back into the workspace.', 'warn');
      return;
    }
    runtime()?.applyDraft?.(deepClone(draft));
    setCompareStatus(`${item.label || 'Compare item'} pushed back into the workspace.`, 'success');
  }

  function rebuildShellFromInspector() {
    const draft = getContextDraft();
    if (!draft) {
      setCompareStatus('Neo could not rebuild the workspace because this output has no reusable payload yet.', 'warn');
      return;
    }
    runtime()?.applyDraft?.(deepClone(draft));
    setCompareStatus('Shell rebuilt from the selected output settings. Source and mask files are not restored automatically.', 'success');
  }

  async function copyPromptPackFromInspector() {
    const payload = inspectorState.job?.payload || {};
    const positive = String(payload.positive || inspectorState.draft?.positive || '').trim();
    const negative = String(payload.negative || inspectorState.draft?.negative || '').trim();
    const text = [positive ? `Positive:\n${positive}` : '', negative ? `Negative:\n${negative}` : ''].filter(Boolean).join('\n\n');
    if (!text) {
      setCompareStatus('This output does not have a prompt pack to copy yet.', 'warn');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCompareStatus('Prompt pack copied to clipboard.', 'success');
    } catch (_) {
      setCompareStatus('Clipboard copy failed in the browser.', 'error');
    }
  }

  function reuseSeedFromInspector() {
    const seed = inspectorState.job?.payload?.seed ?? inspectorState.draft?.seed;
    if (seed === '' || seed == null) {
      setCompareStatus('This output does not expose a reusable seed.', 'warn');
      return;
    }
    const el = $('generation-seed');
    if (!el) return;
    el.value = String(seed);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    setCompareStatus(`Seed ${seed} pushed into the workspace.`, 'success');
  }

  function setInspectorOutputAsActive() {
    const output = inspectorState.output;
    const rt = runtime();
    if (!output?.view_url || !rt?.activateOutput) {
      setCompareStatus('Pick a rendered image first so Neo knows which output should become active.', 'warn');
      return;
    }
    if (isInspectorOutputActive()) {
      setCompareStatus('That image is already the active preview.', 'success');
      return;
    }
    rt.activateOutput({ ...output }, { label: 'Active output' });
    setCompareStatus('Inspector image is now the active preview. Later finish passes can build on this state.', 'success');
  }

  function syncInspectorToActiveOutput() {
    const active = getActiveOutput();
    if (!active) {
      setCompareStatus('There is no active preview image to sync from yet.', 'warn');
      return;
    }
    const job = runtime()?.getLatestJob?.() || inspectorState.job || null;
    const draft = inspectorState.draft || (job?.payload ? payloadToDraft(job.payload) : null);
    setInspectorContext(active, job, draft, 'runtime');
    setCompareStatus('Output inspector synced to the current active preview.', 'success');
  }


  function buildImportedOutputFromFile(file) {
    if (!(file instanceof File)) return null;
    const viewUrl = URL.createObjectURL(file);
    return {
      id: `imported-${Date.now()}`,
      filename: file.name,
      saved_filename: file.name,
      saved_path: 'Imported into Neo output preview',
      view_url: viewUrl,
      size_bytes: file.size || 0,
      imported: true,
    };
  }

  function handleInspectorImportSelection(event) {
    const file = event?.target?.files?.[0] || null;
    if (!file) return;
    const imported = buildImportedOutputFromFile(file);
    if (!imported) {
      setCompareStatus('Neo could not read that file as an output preview.', 'error');
      return;
    }
    const rt = runtime();
    const fallbackJob = rt?.getLatestJob?.() || inspectorState.job || null;
    const fallbackDraft = inspectorState.draft || (fallbackJob?.payload ? payloadToDraft(fallbackJob.payload) : null);
    setInspectorContext(imported, fallbackJob, fallbackDraft, 'imported');
    rt?.activateOutput?.({ ...imported }, { label: `Imported output · ${file.name}` });
    setCompareStatus('Imported image is now the active preview and the current output-inspector target.', 'success');
    if (event?.target) event.target.value = '';
  }

  function promptInspectorImportImage() {
    $('generation-inspector-import-image')?.click();
  }


  function openInspectorLineageOutput(key) {
    const rt = runtime();
    const output = rt?.findLineageOutput?.(key) || null;
    if (!output?.view_url) {
      setCompareStatus('Neo could not reopen that lineage image yet.', 'warn');
      return;
    }
    const activeJob = rt?.getLatestJob?.() || inspectorState.job || null;
    const draft = inspectorState.draft || (activeJob?.payload ? payloadToDraft(activeJob.payload) : null);
    setInspectorContext(output, activeJob, draft, 'lineage');
    rt?.activateOutput?.({ ...output }, { label: output.saved_filename || output.filename || 'Lineage output' });
    setCompareStatus('Lineage image reopened in Output Reuse.', 'success');
  }

  function sendInspectorOutputTo(mode) {
    const output = inspectorState.output;
    const rt = runtime();
    if (!output?.view_url || !rt?.activateOutput || !rt?.sendPreviewToMode) {
      setCompareStatus('Pick a rendered image first so Neo knows which output to reuse.', 'warn');
      return;
    }
    rt.activateOutput({ ...output }, { label: `Reuse → ${mode}` });
    rt.sendPreviewToMode(mode).catch?.(() => {});
  }

  function runInspectorHires() {
    const output = inspectorState.output;
    const rt = runtime();
    if (!output?.view_url || !rt?.activateOutput || !rt?.runPreviewHiresFix) {
      setCompareStatus('Pick a rendered image first so Neo knows which output to polish.', 'warn');
      return;
    }
    rt.activateOutput({ ...output }, { label: 'Reuse → hires polish' });
    rt.runPreviewHiresFix().catch?.(() => {});
  }

  function runInspectorDetailer() {
    const output = inspectorState.output;
    const rt = runtime();
    if (!output?.view_url || !rt?.activateOutput || !rt?.runPreviewDetailerPass) {
      setCompareStatus('Pick a rendered image first so Neo knows which output to repair.', 'warn');
      return;
    }
    rt.activateOutput({ ...output }, { label: 'Reuse → selective repair' });
    rt.runPreviewDetailerPass().catch?.(() => {});
  }

  function runInspectorIdentityRescue() {
    const output = inspectorState.output;
    const rt = runtime();
    if (!output?.view_url || !rt?.activateOutput || !rt?.runPreviewIdentityRescuePass) {
      setCompareStatus('Pick a rendered image first so Neo knows which output should go through Identity Rescue.', 'warn');
      return;
    }
    rt.activateOutput({ ...output }, { label: 'Reuse → identity rescue' });
    rt.runPreviewIdentityRescuePass().catch?.(() => {});
  }
  function renderCompareSession() {
    const host = $('generation-compare-list');
    if (!host) return;
    if (!compareState.items.length) {
      host.innerHTML = '<div class="neo-smart-empty">No compare items yet. Queue a compare set or capture a current winner from the live preview.</div>';
      return;
    }
    host.innerHTML = `<div class="neo-compare-grid">${compareState.items.map(item => {
      const winner = compareState.winnerId === item.id;
      const thumb = item.output?.view_url ? `<img src="${escapeHtml(item.output.view_url)}" alt="${escapeHtml(item.label || 'Compare output')}" class="neo-compare-thumb" />` : `<div class="neo-compare-thumb-empty">Waiting for output</div>`;
      const status = String(item.state || 'queued');
      const metaBits = [item.jobId ? `job ${item.jobId.slice(0, 8)}` : '', item.promptId ? `prompt ${escapeHtml(String(item.promptId).slice(0, 8))}` : '', item.error ? escapeHtml(item.error) : ''].filter(Boolean).join(' · ');
      return `
        <div class="neo-compare-item${winner ? ' is-winner' : ''}">
          <div class="neo-compare-item-head">
            <div>
              <div class="neo-compare-item-title">${escapeHtml(item.label || 'Compare item')}</div>
              <div class="neo-compare-item-subtitle">${metaBits || 'Waiting for queue updates...'}</div>
            </div>
            <span class="neo-guide-chip neo-capability-chip ${compareStatusTone(status)}">${escapeHtml(winner ? 'Winner' : status)}</span>
          </div>
          <button class="neo-compare-thumb-shell" type="button" data-compare-action="preview" data-compare-id="${escapeHtml(item.id)}">${thumb}</button>
          <div class="neo-compare-actions">
            <button class="btn btn-small" type="button" data-compare-action="preview" data-compare-id="${escapeHtml(item.id)}">Preview</button>
            <button class="btn btn-small" type="button" data-compare-action="apply" data-compare-id="${escapeHtml(item.id)}">Use workspace</button>
            <button class="btn btn-small" type="button" data-compare-action="winner" data-compare-id="${escapeHtml(item.id)}">${winner ? 'Unmark' : 'Mark winner'}</button>
            <button class="btn btn-small" type="button" data-compare-action="remove" data-compare-id="${escapeHtml(item.id)}">Remove</button>
          </div>
        </div>
      `;
    }).join('')}</div>`;
  }

  function renderOutputInspector() {
    const host = $('generation-output-inspector-panel');
    if (!host) return;
    const output = inspectorState.output;
    const job = inspectorState.job;
    const payload = job?.payload || {};
    if (!output && !job) {
      host.innerHTML = `
        <div class="neo-smart-card-header">
          <div>
            <div class="neo-smart-title">Output Reuse</div>
            <div class="neo-smart-subtitle">Pick a generated image and Neo will turn it into a reusable recipe card.</div>
          </div>
          <div class="neo-smart-actions">
            <button class="btn btn-small" id="btn-generation-inspector-import-empty" type="button">Load image as output</button>
          </div>
        </div>
        <div class="neo-smart-card-body">
          <div class="neo-smart-empty">Nothing is selected yet. Click a generated image from the preview strip or the compare session to inspect it here — or load an external image straight into the output preview.</div>
          <input accept="image/*" class="hidden" id="generation-inspector-import-image" type="file" />
        </div>
      `;
      $('btn-generation-inspector-import-empty')?.addEventListener('click', promptInspectorImportImage);
      $('generation-inspector-import-image')?.addEventListener('change', handleInspectorImportSelection);
      return;
    }
    const promptPositive = String(payload.positive || inspectorState.draft?.positive || '').trim();
    const promptNegative = String(payload.negative || inspectorState.draft?.negative || '').trim();
    const chips = [
      payload.mode ? `Mode · ${payload.mode}` : '',
      payload.width && payload.height ? `Size · ${payload.width}×${payload.height}` : '',
      payload.seed != null ? `Seed · ${payload.seed}` : '',
      payload.steps != null ? `Steps · ${payload.steps}` : '',
      payload.cfg != null ? `CFG · ${formatMaybeNumber(payload.cfg)}` : '',
      payload.sampler ? `Sampler · ${payload.sampler}` : '',
      payload.checkpoint ? `Model · ${basename(payload.checkpoint)}` : '',
      Array.isArray(payload.loras) && payload.loras.length ? `LoRAs · ${payload.loras.length}` : '',
      Array.isArray(payload.controlnet_units) && payload.controlnet_units.length ? `ControlNet · ${payload.controlnet_units.length}` : '',
      Array.isArray(payload.ipadapter_units) && payload.ipadapter_units.length ? `IP-Adapter · ${payload.ipadapter_units.length}` : '',
    ].filter(Boolean);
    const activeNow = isInspectorOutputActive();
    const lineage = runtime()?.getOutputLineage?.(output) || { chain: [], children: [] };
    const lineageChain = Array.isArray(lineage.chain) ? lineage.chain : [];
    const lineageChildren = Array.isArray(lineage.children) ? lineage.children : [];
    const lineageHtml = (lineageChain.length > 1 || lineageChildren.length)
      ? `<div class="neo-output-prompts" style="margin-top:14px;">
          <div class="neo-output-prompt-block">
            <div class="neo-output-prompt-label">Lineage</div>
            <div class="neo-output-prompt-copy">${lineageChain.length ? lineageChain.map((entry, index) => `<span class="neo-output-chip">${escapeHtml(index === 0 ? 'Base' : (entry.stage || 'Pass'))} · ${escapeHtml(entry.output?.saved_filename || entry.output?.filename || 'Output')}</span>`).join('') : '<span class="muted">This output does not have a recorded parent chain yet.</span>'}</div>
          </div>
          <div class="neo-output-prompt-block">
            <div class="neo-output-prompt-label">Child pass history</div>
            <div class="neo-output-prompt-copy">${lineageChildren.length ? `<div class="neo-output-action-row">${lineageChildren.map(entry => `<button class="btn btn-small" type="button" data-lineage-output-key="${escapeHtml(entry.key)}">${escapeHtml(entry.stage || 'Derived pass')} · ${escapeHtml(entry.output?.saved_filename || entry.output?.filename || 'Output')}</button>`).join('')}</div>` : '<span class="muted">No child passes have been recorded from this output yet.</span>'}</div>
          </div>
        </div>`
      : '';
    host.innerHTML = `
      <div class="neo-smart-card-header">
        <div>
          <div class="neo-smart-title">Output Reuse</div>
          <div class="neo-smart-subtitle">Reuse a good result instead of rebuilding it from memory later.</div>
        </div>
        <div class="neo-smart-actions">
          <button class="btn btn-small" id="btn-generation-inspector-rebuild" type="button">Rebuild workspace</button>
          <button class="btn btn-small" id="btn-generation-inspector-copy" type="button">Copy prompt pack</button>
          <button class="btn btn-small" id="btn-generation-inspector-seed" type="button">Reuse seed</button>
          <button class="btn btn-small" id="btn-generation-inspector-capture" type="button">Add to compare</button>
        </div>
      </div>
      <div class="neo-smart-card-body">
        <div class="neo-output-active-shell${activeNow ? ' is-current' : ''}">
          <div class="neo-output-active-copy">
            <div class="neo-output-prompt-label">Active output</div>
            <div class="neo-output-active-title">${activeNow ? 'Inspector image is driving the active preview' : 'Inspector image is not the active preview yet'}</div>
            <div class="neo-output-active-note">${escapeHtml(getActiveOutputLabel())}</div>
          </div>
          <div class="neo-output-action-row">
            <button class="btn btn-small" id="btn-generation-inspector-set-active" type="button" ${activeNow ? 'disabled' : ''}>${activeNow ? 'Already active' : 'Set as active preview'}</button>
            <button class="btn btn-small" id="btn-generation-inspector-sync-active" type="button">Use current preview here</button>
            <button class="btn btn-small" id="btn-generation-inspector-import" type="button">Load image as output</button>
            <input accept="image/*" class="hidden" id="generation-inspector-import-image" type="file" />
          </div>
        </div>
        <div class="neo-output-inspector-top">
          <div class="neo-output-inspector-thumb-wrap">
            ${output?.view_url ? `<img src="${escapeHtml(output.view_url)}" alt="${escapeHtml(output.saved_filename || output.filename || 'Output preview')}" class="neo-output-inspector-thumb" />` : '<div class="neo-compare-thumb-empty">No preview image</div>'}
          </div>
          <div class="neo-output-inspector-copy">
            <div class="neo-output-inspector-name">${escapeHtml(output?.saved_filename || output?.filename || 'Selected output')}</div>
            ${output?.saved_path ? `<div class="neo-output-inspector-path">${escapeHtml(output.saved_path)}</div>` : ''}
            ${chips.length ? `<div class="neo-output-chip-row">${chips.map(chip => `<span class="neo-output-chip">${escapeHtml(chip)}</span>`).join('')}</div>` : ''}
            <div class="neo-output-action-row">
              <button class="btn btn-small" id="btn-generation-inspector-img2img" type="button">Send to Img2img</button>
              <button class="btn btn-small" id="btn-generation-inspector-inpaint" type="button">Send to Inpaint</button>
              <button class="btn btn-small" id="btn-generation-inspector-outpaint" type="button">Send to Outpaint</button>
              <button class="btn btn-small" id="btn-generation-inspector-hires" type="button">Hires from this</button>
              <button class="btn btn-small" id="btn-generation-inspector-detailer" type="button">Repair from this</button>
              <button class="btn btn-small" id="btn-generation-inspector-identity" type="button">Identity rescue</button>
            </div>
          </div>
        </div>
        ${lineageHtml}
        <div class="neo-output-prompts">
          <div class="neo-output-prompt-block">
            <div class="neo-output-prompt-label">Positive prompt</div>
            <div class="neo-output-prompt-copy">${promptPositive ? escapeHtml(promptPositive) : '<span class="muted">No prompt recorded.</span>'}</div>
          </div>
          <div class="neo-output-prompt-block">
            <div class="neo-output-prompt-label">Negative prompt</div>
            <div class="neo-output-prompt-copy">${promptNegative ? escapeHtml(promptNegative) : '<span class="muted">No negative prompt recorded.</span>'}</div>
          </div>
        </div>
      </div>
    `;

    $('btn-generation-inspector-rebuild')?.addEventListener('click', rebuildShellFromInspector);
    $('btn-generation-inspector-copy')?.addEventListener('click', () => { copyPromptPackFromInspector().catch?.(() => {}); });
    $('btn-generation-inspector-seed')?.addEventListener('click', reuseSeedFromInspector);
    $('btn-generation-inspector-capture')?.addEventListener('click', captureCurrentOutput);
    $('btn-generation-inspector-set-active')?.addEventListener('click', setInspectorOutputAsActive);
    $('btn-generation-inspector-sync-active')?.addEventListener('click', syncInspectorToActiveOutput);
    $('btn-generation-inspector-import')?.addEventListener('click', promptInspectorImportImage);
    $('generation-inspector-import-image')?.addEventListener('change', handleInspectorImportSelection);
    $('btn-generation-inspector-img2img')?.addEventListener('click', () => sendInspectorOutputTo('img2img'));
    $('btn-generation-inspector-inpaint')?.addEventListener('click', () => sendInspectorOutputTo('inpaint'));
    $('btn-generation-inspector-outpaint')?.addEventListener('click', () => sendInspectorOutputTo('outpaint'));
    $('btn-generation-inspector-hires')?.addEventListener('click', runInspectorHires);
    $('btn-generation-inspector-detailer')?.addEventListener('click', runInspectorDetailer);
    $('btn-generation-inspector-identity')?.addEventListener('click', runInspectorIdentityRescue);
    host.querySelectorAll('[data-lineage-output-key]').forEach(btn => btn.addEventListener('click', () => openInspectorLineageOutput(btn.getAttribute('data-lineage-output-key') || '')));
  }

  function bindEvents() {
    $('generation-compare-axis')?.addEventListener('change', updateCompareAxisUI);
    $('btn-generation-compare-run')?.addEventListener('click', queueCompareSet);
    $('btn-generation-compare-capture')?.addEventListener('click', captureCurrentOutput);
    $('btn-generation-compare-clear')?.addEventListener('click', () => {
      compareState.items = [];
      compareState.winnerId = '';
      stopComparePolling();
      renderCompareSession();
      setCompareStatus('Compare session cleared.', 'success');
    });
    $('generation-compare-list')?.addEventListener('click', e => {
      const btn = e.target instanceof HTMLElement ? e.target.closest('[data-compare-action]') : null;
      if (!btn) return;
      const action = btn.getAttribute('data-compare-action') || '';
      const id = btn.getAttribute('data-compare-id') || '';
      if (!id) return;
      if (action === 'preview') previewCompareItem(id);
      else if (action === 'apply') applyCompareItemToShell(id);
      else if (action === 'winner') markCompareWinner(id);
      else if (action === 'remove') removeCompareItem(id);
    });

    window.addEventListener('neo:generation-output-selected', event => {
      const detail = event?.detail || {};
      setInspectorContext(detail.output || null, detail.job || null, detail.job?.payload ? payloadToDraft(detail.job.payload) : null, 'runtime');
    });

    window.addEventListener('neo:generation-job-updated', event => {
      const detail = event?.detail || {};
      const job = detail.job || null;
      if (!job?.id) return;
      let changed = false;
      compareState.items.forEach(item => {
        if (item.jobId && item.jobId === job.id) {
          item.state = String(job.state || item.state || 'queued');
          item.job = job;
          item.outputs = Array.isArray(job.outputs) ? job.outputs.slice() : [];
          item.output = item.outputs[0] || item.output || null;
          item.draft = job.payload ? payloadToDraft(job.payload) : item.draft;
          changed = true;
        }
      });
      if (changed) renderCompareSession();
      if (!inspectorState.output && job?.outputs?.length) setInspectorContext(job.outputs[0], job, job.payload ? payloadToDraft(job.payload) : null, 'runtime');
    });
  }

  ready(() => {
    if (!document.querySelector(ROOT_SELECTOR)) return;
    createPowerPanel();
    bindEvents();
    updateCompareAxisUI();
    renderCompareSession();
    renderOutputInspector();
    syncInspectorFromRuntime();
  });
})();
