(function () {
  const VERSION = 'image-state-v1';
  const DEFAULT_STATE = Object.freeze({
    version: VERSION,
    mode: 'txt2img',
    workflow_type: 'txt2img',
    build: Object.freeze({
      width: 1024,
      height: 1024,
      size_source: 'default',
      family: '',
      checkpoint: '',
      sampler: '',
      scheduler: '',
      seed: null,
      steps: null,
      cfg: null,
    }),
    prompt: Object.freeze({
      positive: '',
      negative: '',
      stack_source: 'ui',
    }),
    source: Object.freeze({
      active_source_image: null,
      selected_output_id: null,
      selected_job_id: null,
      preview_action_target: null,
      selected_output_snapshot: null,
    }),
    modules: Object.freeze({
      scene_director: null,
      dynamic_thresholding: Object.freeze({ enabled: false, preset: 'off', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 1.0, auto_disable_low_cfg: true, auto_disable_family: true }),
      ipadapter: null,
      controlnet: null,
      lora_stack: null,
      embeddings: null,
      finish_action: null,
    }),
    meta: Object.freeze({
      last_update_source: 'init',
      last_updated_at: null,
      dirty_keys: Object.freeze([]),
    }),
  });

  function clone(value) {
    if (value == null || typeof value !== 'object') return value;
    try { return structuredClone(value); } catch (_) { return JSON.parse(JSON.stringify(value)); }
  }

  function isPlainObject(value) {
    return !!value && typeof value === 'object' && !Array.isArray(value);
  }

  function mergeDeep(base, patch) {
    const output = clone(base) || {};
    if (!isPlainObject(patch)) return output;
    Object.entries(patch).forEach(([key, value]) => {
      if (isPlainObject(value) && isPlainObject(output[key])) output[key] = mergeDeep(output[key], value);
      else output[key] = clone(value);
    });
    return output;
  }

  function validDimension(value) {
    const n = parseInt(value, 10);
    if (!Number.isFinite(n) || n < 64 || n > 8192) return null;
    return n;
  }

  function normalizeSize(width, height, fallback) {
    const w = validDimension(width);
    const h = validDimension(height);
    if (w && h) return { width: w, height: h };
    return { width: fallback?.width || 1024, height: fallback?.height || 1024 };
  }

  function normalizeDynamicThresholding(value) {
    const source = isPlainObject(value) ? value : {};
    const preset = String(source.preset || (source.enabled ? 'advanced' : 'off')).trim().toLowerCase();
    const mode = String(source.mode || 'simple').trim().toLowerCase() === 'full' ? 'full' : 'simple';
    const mimic = Number(source.mimic_scale ?? source.mimic_cfg ?? 7.0);
    const percentile = Number(source.threshold_percentile ?? source.percentile ?? 1.0);
    const enabled = preset === 'off' ? false : !!source.enabled;
    return {
      enabled,
      preset: ['off','safe','detail_push','advanced'].includes(preset) ? preset : (enabled ? 'advanced' : 'off'),
      mode,
      node: mode === 'full' ? 'DynamicThresholdingFull' : 'DynamicThresholdingSimple',
      mimic_scale: Number.isFinite(mimic) ? Math.max(1, Math.min(30, mimic)) : 7.0,
      threshold_percentile: Number.isFinite(percentile) ? Math.max(0.80, Math.min(1.00, percentile)) : 1.0,
      auto_disable_low_cfg: source.auto_disable_low_cfg !== false,
      auto_disable_family: source.auto_disable_family !== false,
    };
  }

  const WORKFLOW_MODES = Object.freeze(['txt2img', 'img2img', 'inpaint', 'outpaint']);
  const BATCH_FORCE_ONE_WORKFLOWS = Object.freeze(['img2img', 'inpaint', 'outpaint']);
  const OUTPUT_POLICY_ALIASES = Object.freeze({
    new_run: 'new_current_run',
    new_current_run: 'new_current_run',
    append: 'append_derived',
    append_derived: 'append_derived',
    replace: 'replace_selected',
    replace_selected: 'replace_selected',
    preview: 'preview_only',
    preview_only: 'preview_only',
  });

  function normalizeOutputPolicy(value, mode = 'txt2img') {
    const raw = String(value || 'new_current_run').trim().toLowerCase() || 'new_current_run';
    let effective = OUTPUT_POLICY_ALIASES[raw] || 'new_current_run';
    const warnings = [];
    if (!OUTPUT_POLICY_ALIASES[raw]) {
      warnings.push({ code: 'output_policy_reset', message: 'Unknown output policy; using New run.', target: 'output_policy', severity: 'warning' });
    }
    if (BATCH_FORCE_ONE_WORKFLOWS.includes(mode) && effective === 'replace_selected') {
      warnings.push({ code: 'output_policy_replace_requires_confirmation', message: `${mode} queues as New run until explicit replace confirmation exists.`, target: 'output_policy', severity: 'warning' });
      effective = 'new_current_run';
    }
    return { requested: raw, effective, warnings };
  }

  function readBatchSizeFromDom() {
    if (typeof document === 'undefined') return 1;
    const raw = document.getElementById('generation-batch-size')?.value || '1';
    const n = parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : 1;
  }

  function buildBatchPolicy(mode, requested) {
    const safeRequested = Math.max(1, parseInt(requested, 10) || 1);
    const forceOne = BATCH_FORCE_ONE_WORKFLOWS.includes(mode);
    return {
      requested: safeRequested,
      effective: forceOne ? 1 : safeRequested,
      policy: forceOne ? 'force_1' : 'allow',
      reason: forceOne ? 'source_image_workflow' : '',
      visible: true,
    };
  }

  function normalizeWorkflowMode(value, fallback = 'txt2img') {
    const raw = String(value || '').trim().toLowerCase();
    if (WORKFLOW_MODES.includes(raw)) return raw;
    const fb = String(fallback || '').trim().toLowerCase();
    return WORKFLOW_MODES.includes(fb) ? fb : 'txt2img';
  }

  function normalize(raw) {
    const merged = mergeDeep(DEFAULT_STATE, raw || {});
    const size = normalizeSize(merged.build?.width, merged.build?.height, DEFAULT_STATE.build);
    merged.version = VERSION;
    const normalizedMode = normalizeWorkflowMode(merged.mode || merged.workflow_type, DEFAULT_STATE.mode);
    merged.mode = normalizedMode;
    merged.workflow_type = normalizedMode;
    merged.build = mergeDeep(merged.build || {}, size);
    merged.modules = mergeDeep(merged.modules || {}, {
      dynamic_thresholding: normalizeDynamicThresholding(merged.modules?.dynamic_thresholding),
    });
    merged.meta = mergeDeep(merged.meta || {}, {
      last_updated_at: merged.meta?.last_updated_at || new Date().toISOString(),
      dirty_keys: Array.isArray(merged.meta?.dirty_keys) ? merged.meta.dirty_keys : [],
    });
    return merged;
  }

  function parsePayloadSize(payload) {
    if (!isPlainObject(payload)) return null;
    const sizeText = payload.size || payload.resolution || payload.size_preset || payload.generation_size || payload.image_size || payload.output_size;
    let width = payload.width ?? payload.generation_width ?? payload.image_width ?? payload.canvas_width;
    let height = payload.height ?? payload.generation_height ?? payload.image_height ?? payload.canvas_height;
    if ((!width || !height) && typeof sizeText === 'string') {
      const match = sizeText.match(/([1-8][0-9]{2,3})\s*[x×]\s*([1-8][0-9]{2,3})/i);
      if (match) { width = match[1]; height = match[2]; }
    }
    const parsed = normalizeSize(width, height, null);
    if (!parsed.width || !parsed.height) return null;
    return parsed;
  }

  let currentState = normalize(window.NeoImageStateInitial || {});
  const listeners = new Set();

  function emit(detail) {
    const eventDetail = { state: getState(), ...(detail || {}) };
    listeners.forEach(listener => { try { listener(eventDetail); } catch (_) {} });
    try { window.dispatchEvent(new CustomEvent('neo-image-state-changed', { detail: eventDetail })); } catch (_) {}
  }

  function getState() { return clone(currentState); }

  function dispatchWorkflowModeChanged(previous, state, detail) {
    const eventDetail = {
      previous_state: clone(previous),
      previous_mode: previous?.mode || previous?.workflow_type || 'txt2img',
      mode: state?.mode || state?.workflow_type || 'txt2img',
      workflow_type: state?.workflow_type || state?.mode || 'txt2img',
      state: clone(state),
      ...(isPlainObject(detail) ? detail : {}),
    };
    try { window.dispatchEvent(new CustomEvent('neo:image:workflow-mode-changed', { detail: eventDetail })); } catch (_) {}
  }

  function setState(patch, source = 'unknown') {
    const previous = currentState;
    const next = normalize(mergeDeep(currentState, patch || {}));
    next.meta = mergeDeep(next.meta, {
      last_update_source: source,
      last_updated_at: new Date().toISOString(),
      dirty_keys: Object.keys(patch || {}),
    });
    currentState = next;
    emit({ previous: clone(previous), source });
    return getState();
  }

  function setWorkflowMode(mode, options = {}) {
    const previous = getState();
    const nextMode = normalizeWorkflowMode(mode, previous.mode || previous.workflow_type || DEFAULT_STATE.mode);
    const source = String(options?.source || options?.reason || 'workflow-mode').trim() || 'workflow-mode';
    const next = setState({
      mode: nextMode,
      workflow_type: nextMode,
      meta: {
        workflow_switch_reason: String(options?.reason || source || '').trim(),
        workflow_switch_source: source,
      },
    }, source);
    if ((previous.mode || previous.workflow_type) !== nextMode || options?.force_event) {
      dispatchWorkflowModeChanged(previous, next, {
        source,
        reason: String(options?.reason || source || '').trim(),
        requested_mode: String(mode || '').trim(),
      });
    }
    return next;
  }

  function updateBuild(patch, source = 'build') {
    return setState({ build: patch || {} }, source);
  }

  function updatePrompt(patch, source = 'prompt') {
    return setState({ prompt: patch || {} }, source);
  }

  function updateSource(patch, source = 'source') {
    return setState({ source: patch || {} }, source);
  }

  function updateModule(name, value, source = 'module') {
    if (!name) return getState();
    return setState({ modules: { [name]: value } }, source);
  }

  function ingestGenerationPayload(payload, source = 'generation-payload') {
    if (typeof payload === 'string') {
      try { payload = JSON.parse(payload); } catch (_) { return getState(); }
    }
    if (!isPlainObject(payload)) return getState();
    const patch = {};
    const mode = payload.mode || payload.workflow_type || payload.refine_mode;
    if (mode) {
      const normalizedMode = normalizeWorkflowMode(mode, currentState.mode || currentState.workflow_type || DEFAULT_STATE.mode);
      patch.mode = normalizedMode;
      patch.workflow_type = normalizedMode;
    }
    const size = parsePayloadSize(payload);
    if (size) patch.build = { ...size, size_source: source };
    const positive = payload.prompt ?? payload.positive ?? payload.positive_prompt;
    const negative = payload.negative_prompt ?? payload.negative;
    if (positive != null || negative != null) patch.prompt = {
      ...(positive != null ? { positive: String(positive) } : {}),
      ...(negative != null ? { negative: String(negative) } : {}),
    };
    if (payload.generationSelectedOutputSnapshot || payload.generationPreviewActionTarget || payload.source_image_name) {
      patch.source = {
        selected_output_snapshot: payload.generationSelectedOutputSnapshot || currentState.source.selected_output_snapshot,
        preview_action_target: payload.generationPreviewActionTarget || currentState.source.preview_action_target,
        active_source_image: payload.source_image_name || currentState.source.active_source_image,
      };
    }
    if (payload.scene_director || payload.scene_director_state || payload.scene_director_v052_scene_json) {
      patch.modules = { ...(patch.modules || {}), scene_director: payload.scene_director || payload.scene_director_state || payload.scene_director_v052_scene_json };
    }
    if (payload.dynamic_thresholding || payload.modules?.dynamic_thresholding) {
      patch.modules = { ...(patch.modules || {}), dynamic_thresholding: normalizeDynamicThresholding(payload.dynamic_thresholding || payload.modules.dynamic_thresholding) };
    }
    return setState(patch, source);
  }



  function normalizeOutputReference(value, sourceType) {
    if (!isPlainObject(value)) {
      if (typeof value === 'string' && value.trim()) return { source_type: sourceType || 'selected_output', filename: value.trim() };
      return null;
    }
    const ref = clone(value) || {};
    ref.source_type = ref.source_type || sourceType || 'selected_output';
    ref.output_id = ref.output_id || ref.id || ref.outputId || null;
    ref.job_id = ref.job_id || ref.jobId || null;
    ref.filename = ref.filename || ref.name || ref.image || ref.path || null;
    ref.locked_at = ref.locked_at || new Date().toISOString();
    return ref;
  }

  function lockSelectedOutput(output, source = 'results-selection') {
    const ref = normalizeOutputReference(output, 'selected_output');
    if (!ref) return getState();
    return updateSource({
      selected_output_id: ref.output_id || currentState.source.selected_output_id || null,
      selected_job_id: ref.job_id || currentState.source.selected_job_id || null,
      selected_output_snapshot: ref,
      preview_action_target: ref,
      active_source_image: ref.filename || currentState.source.active_source_image || null,
      explicit_source_type: 'selected_output',
      locked_source: ref,
    }, source);
  }

  function lockPreviewOutput(output, source = 'preview-action-source') {
    const ref = normalizeOutputReference(output, 'preview_output');
    if (!ref) return getState();
    return updateSource({
      selected_output_id: ref.output_id || currentState.source.selected_output_id || null,
      selected_job_id: ref.job_id || currentState.source.selected_job_id || null,
      selected_output_snapshot: ref,
      preview_action_target: ref,
      active_source_image: ref.filename || ref.source_image_name || currentState.source.active_source_image || null,
      explicit_source_type: 'preview_output',
      locked_source: ref,
      source_route_state: {
        source_kind: 'preview_output',
        source_id: ref.output_id || ref.filename || '',
        source_name: ref.filename || ref.source_image_name || '',
        routed_at: new Date().toISOString(),
        route_source: source,
      },
    }, source);
  }

  function lockUploadedSource(sourceImageName, source = 'source-upload') {
    const name = typeof sourceImageName === 'string' ? sourceImageName.trim() : '';
    if (!name) return getState();
    const ref = { source_type: 'uploaded_source', filename: name, source_image_name: name, locked_at: new Date().toISOString() };
    return updateSource({
      active_source_image: name,
      explicit_source_type: 'uploaded_source',
      locked_source: ref,
      preview_action_target: ref,
    }, source);
  }

  function clearOutputSelection(source = 'clear-output-selection') {
    return updateSource({
      selected_output_id: null,
      selected_job_id: null,
      preview_action_target: null,
      selected_output_snapshot: null,
      locked_source: null,
      explicit_source_type: null,
    }, source);
  }

  function resolvePreviewSource(options = {}) {
    const state = getState();
    const source = state.source || {};
    const explicit = normalizeOutputReference(options.target || options.output || source.locked_source || source.preview_action_target || source.selected_output_snapshot, options.source_type);
    const activeSource = options.source_image_name || source.active_source_image || '';
    if (explicit) return { locked: true, source_type: explicit.source_type || 'selected_output', target: explicit };
    if (activeSource) return { locked: true, source_type: 'uploaded_source', source_image_name: activeSource, target: { source_type: 'uploaded_source', filename: activeSource, source_image_name: activeSource } };
    return { locked: false, source_type: 'none', target: null, reason: 'missing_explicit_source' };
  }

  function readOutpaintExpansionFromDom() {
    if (typeof document === 'undefined') return { left: 0, top: 0, right: 0, bottom: 0 };
    const read = (ids) => {
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        const n = parseInt(String(el.value ?? el.getAttribute?.('value') ?? '0').replace(/[^0-9-]/g, ''), 10);
        if (Number.isFinite(n)) return Math.max(0, n);
      }
      return 0;
    };
    return {
      left: read(['generation-outpaint-left', 'outpaint-left', 'outpaint_left']),
      top: read(['generation-outpaint-top', 'outpaint-top', 'outpaint_top']),
      right: read(['generation-outpaint-right', 'outpaint-right', 'outpaint_right']),
      bottom: read(['generation-outpaint-bottom', 'outpaint-bottom', 'outpaint_bottom']),
    };
  }

  function validateWorkflowState(options = {}) {
    const state = getState();
    const mode = normalizeWorkflowMode(options.mode || state.mode || state.workflow_type || 'txt2img');
    const source = state.source || {};
    const resolvedSource = resolvePreviewSource({
      target: options.target || options.output || source.locked_source || source.preview_action_target || source.selected_output_snapshot,
      source_image_name: options.source_image_name || options.sourceName || source.active_source_image,
      source_type: options.sourceKind || options.source_type || source.explicit_source_type,
    });
    const outpaint = options.outpaintExpansion || options.outpaint_expansion || readOutpaintExpansionFromDom();
    const left = Number(outpaint.left || 0);
    const top = Number(outpaint.top || 0);
    const right = Number(outpaint.right || 0);
    const bottom = Number(outpaint.bottom || 0);
    const hasSource = mode === 'txt2img' || !!resolvedSource.locked;
    const maskName = String(options.mask_image_name || source.mask_image_name || '').trim();
    const hasMask = mode !== 'inpaint' || !!maskName || !!options.maskPresent;
    const hasExpansion = mode !== 'outpaint' || ((left + top + right + bottom) > 0);
    const errors = [];
    const warnings = [];
    const batchPolicy = buildBatchPolicy(mode, options.batch_size || options.batchSize || readBatchSizeFromDom());
    const outputPolicy = normalizeOutputPolicy(options.output_policy || options.outputPolicy || 'new_current_run', mode);
    warnings.push(...outputPolicy.warnings);
    if (batchPolicy.policy === 'force_1' && batchPolicy.requested > 1) {
      warnings.push({ code: 'batch_force_one_required', message: `${mode} is a source-image workflow; batch size will run as 1.`, target: 'batch_size', severity: 'warning' });
    }
    if (!hasSource) errors.push({ code: 'missing_source_image', message: `${mode} requires a source image before queueing.`, target: 'source_image', severity: 'block' });
    if (!hasMask) errors.push({ code: 'missing_mask_image', message: 'inpaint requires a mask image before queueing.', target: 'mask_image', severity: 'block' });
    if (!hasExpansion) errors.push({ code: 'missing_outpaint_expansion', message: 'outpaint requires padding on at least one side before queueing.', target: 'outpaint_expansion', severity: 'block' });
    const validation = {
      valid: errors.length === 0,
      reason: errors[0]?.message || '',
      errors,
      warnings,
      auto_fixes: [],
      workflow: mode,
      mode,
      source_required: mode !== 'txt2img',
      mask_required: mode === 'inpaint',
      source_kind: resolvedSource.source_type || 'none',
      source_id: resolvedSource.target?.output_id || resolvedSource.target?.filename || resolvedSource.source_image_name || '',
      outpaint_expansion: { left: Math.max(0, left || 0), top: Math.max(0, top || 0), right: Math.max(0, right || 0), bottom: Math.max(0, bottom || 0) },
      validation_status: errors.length ? 'blocked' : 'valid',
      batch_policy: batchPolicy,
      output_policy: outputPolicy.effective,
      output_policy_requested: outputPolicy.requested,
    };
    try { window.dispatchEvent(new CustomEvent('neo:image:workflow-validation-changed', { detail: validation })); } catch (_) {}
    return validation;
  }



  function buildWorkflowPayloadState(options = {}) {
    const state = getState();
    const mode = normalizeWorkflowMode(options.mode || state.mode || state.workflow_type || 'txt2img');
    const validation = validateWorkflowState({
      mode,
      target: options.target,
      output: options.output,
      source_image_name: options.source_image_name,
      sourceName: options.sourceName,
      sourceKind: options.sourceKind,
      source_type: options.source_type,
      mask_image_name: options.mask_image_name,
      maskPresent: options.maskPresent,
      outpaintExpansion: options.outpaintExpansion || options.outpaint_expansion,
      batch_size: options.batch_size || options.batchSize,
      output_policy: options.output_policy || options.outputPolicy,
    });
    const source = state.source || {};
    const sourceRoute = isPlainObject(source.source_route_state) ? source.source_route_state : {};
    const outputPolicy = normalizeOutputPolicy(options.output_policy || source.output_policy || state.meta?.output_policy || validation.output_policy || 'new_current_run', mode);
    const requestedOutputPolicy = outputPolicy.effective;
    const batchPolicy = validation.batch_policy || buildBatchPolicy(mode, options.batch_size || options.batchSize || readBatchSizeFromDom());
    const switchReason = String(options.switch_reason || options.reason || state.meta?.workflow_switch_reason || state.meta?.workflow_switch_source || 'payload_collect').trim() || 'payload_collect';
    const rawMode = normalizeWorkflowMode(options.raw_mode || state.meta?.raw_workflow_mode || state.workflow_type || state.mode || mode, mode);
    const sourceKind = String(validation.source_kind || sourceRoute.source_kind || source.explicit_source_type || 'none').trim() || 'none';
    const sourceId = String(validation.source_id || sourceRoute.source_id || source.selected_output_id || source.active_source_image || '').trim();
    return {
      raw_mode: rawMode,
      effective_mode: mode,
      switch_reason: switchReason,
      source_kind: sourceKind,
      source_id: sourceId,
      source_name: String(sourceRoute.source_name || source.active_source_image || validation.source_id || '').trim(),
      output_policy: requestedOutputPolicy,
      output_policy_requested: outputPolicy.requested,
      output_policy_effective: outputPolicy.effective,
      validation_status: validation.validation_status || (validation.valid ? 'valid' : 'blocked'),
      source_required: !!validation.source_required,
      mask_required: !!validation.mask_required,
      outpaint_expansion: validation.outpaint_expansion || { left: 0, top: 0, right: 0, bottom: 0 },
      batch_policy: batchPolicy,
      visible: true,
      owner: 'NeoImageState',
      version: 'phase_i_save_restore_metadata_v1',
    };
  }

  function buildPersistedWorkflowState(options = {}) {
    const workflowState = buildWorkflowPayloadState({
      reason: options.reason || options.switch_reason || 'draft_save',
      output_policy: options.output_policy || options.outputPolicy,
      batch_size: options.batch_size || options.batchSize,
      outpaintExpansion: options.outpaintExpansion || options.outpaint_expansion,
      mask_image_name: options.mask_image_name,
      source_image_name: options.source_image_name,
      sourceKind: options.sourceKind || options.source_kind,
    });
    const state = getState();
    return {
      schema_version: 1,
      owner: 'NeoImageState',
      saved_at: new Date().toISOString(),
      raw_state: {
        mode: workflowState.raw_mode,
        workflow_type: workflowState.raw_mode,
        source_kind: workflowState.source_kind,
        source_id: workflowState.source_id,
        source_name: workflowState.source_name,
        output_policy: workflowState.output_policy_requested || workflowState.output_policy,
        batch_size: workflowState.batch_policy?.requested || options.batch_size || readBatchSizeFromDom(),
      },
      effective_state: {
        mode: workflowState.effective_mode,
        workflow_type: workflowState.effective_mode,
        source_kind: workflowState.source_kind,
        source_id: workflowState.source_id,
        source_name: workflowState.source_name,
        output_policy: workflowState.output_policy_effective || workflowState.output_policy,
        validation_status: workflowState.validation_status,
        batch_policy: workflowState.batch_policy,
        source_required: workflowState.source_required,
        mask_required: workflowState.mask_required,
        outpaint_expansion: workflowState.outpaint_expansion,
      },
      transition: {
        switch_reason: workflowState.switch_reason || 'draft_save',
        restored_by: 'setGenerationWorkflowMode',
        restore_requires_canonical_helper: true,
      },
      source_snapshot: clone(state.source || {}),
      workflow_state: workflowState,
      version: 'phase_i_save_restore_metadata_v1',
    };
  }

  function restoreWorkflowState(persisted, options = {}) {
    if (!isPlainObject(persisted)) return getState();
    const raw = isPlainObject(persisted.raw_state) ? persisted.raw_state : persisted;
    const effective = isPlainObject(persisted.effective_state) ? persisted.effective_state : persisted;
    const sourceSnapshot = isPlainObject(persisted.source_snapshot) ? persisted.source_snapshot : {};
    const mode = normalizeWorkflowMode(options.mode || effective.mode || effective.workflow_type || raw.mode || raw.workflow_type || persisted.effective_mode || persisted.raw_mode || currentState.mode, currentState.mode);
    const outputPolicy = normalizeOutputPolicy(effective.output_policy || raw.output_policy || persisted.output_policy || 'new_current_run', mode);
    const sourcePatch = mergeDeep(sourceSnapshot, {
      explicit_source_type: effective.source_kind || raw.source_kind || sourceSnapshot.explicit_source_type || null,
      active_source_image: effective.source_name || raw.source_name || sourceSnapshot.active_source_image || null,
      selected_output_id: effective.source_id || raw.source_id || sourceSnapshot.selected_output_id || null,
      source_route_state: {
        source_kind: effective.source_kind || raw.source_kind || sourceSnapshot.source_route_state?.source_kind || 'none',
        source_id: effective.source_id || raw.source_id || sourceSnapshot.source_route_state?.source_id || '',
        source_name: effective.source_name || raw.source_name || sourceSnapshot.source_route_state?.source_name || '',
        restored_at: new Date().toISOString(),
        route_source: options.reason || 'draft_restore',
      },
      output_policy: outputPolicy.effective,
    });
    const previous = getState();
    const next = setState({
      mode,
      workflow_type: mode,
      source: sourcePatch,
      meta: {
        raw_workflow_mode: raw.mode || raw.workflow_type || mode,
        workflow_switch_reason: options.reason || persisted.transition?.switch_reason || 'draft_restore',
        workflow_switch_source: 'draft_restore',
        output_policy: outputPolicy.effective,
        restored_workflow_state_version: persisted.version || '',
      },
    }, options.source || 'draft_restore');
    dispatchWorkflowModeChanged(previous, next, {
      source: options.source || 'draft_restore',
      reason: options.reason || 'draft_restore',
      requested_mode: mode,
      restored: true,
    });
    return next;
  }

  function subscribe(listener) {
    if (typeof listener !== 'function') return () => {};
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  function getBuildSize() {
    const state = getState();
    return normalizeSize(state.build?.width, state.build?.height, DEFAULT_STATE.build);
  }



  function readLiveBuildSizeFromDom() {
    if (typeof document === 'undefined') return null;
    const sceneShell = document.getElementById('neo-scene-director-shell');
    const insideSceneDirector = (el) => !!(el && sceneShell && sceneShell.contains(el));
    const valid = (width, height) => {
      const w = validDimension(width);
      const h = validDimension(height);
      return (w && h) ? { width: w, height: h } : null;
    };
    const parseSizeText = (raw) => {
      const text = String(raw || '').replace(/\s+/g, ' ').trim();
      const match = text.match(/(?:^|[^0-9])([1-8][0-9]{2,3})\s*[x×]\s*([1-8][0-9]{2,3})(?:[^0-9]|$)/i);
      return match ? valid(match[1], match[2]) : null;
    };
    const visible = (el) => {
      if (!el || insideSceneDirector(el) || el.closest?.('#neo-scene-director-shell,[hidden],[aria-hidden="true"]')) return false;
      const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
      if (style && (style.display === 'none' || style.visibility === 'hidden')) return false;
      const rect = el.getBoundingClientRect?.();
      return !rect || (rect.width > 0 && rect.height > 0);
    };
    const textOf = (el) => {
      const bits = [];
      if (el?.tagName === 'SELECT') {
        bits.push(el.value || '');
        Array.from(el.selectedOptions || []).forEach(opt => bits.push(opt.value || '', opt.textContent || '', opt.dataset?.size || '', opt.dataset?.resolution || '', opt.getAttribute('data-size') || '', opt.getAttribute('data-resolution') || ''));
      } else bits.push(el?.value ?? '');
      bits.push(el?.dataset?.value || '', el?.dataset?.size || '', el?.dataset?.resolution || '', el?.dataset?.generationSize || '', el?.dataset?.generationResolution || '', el?.getAttribute?.('data-value') || '', el?.getAttribute?.('data-size') || '', el?.getAttribute?.('data-resolution') || '', el?.getAttribute?.('aria-label') || '', el?.getAttribute?.('title') || '', el?.textContent || '');
      return bits.filter(Boolean).join(' ');
    };
    const contextOf = (el) => {
      const bits = [el?.id || '', el?.name || '', el?.className || '', el?.getAttribute?.('aria-label') || '', el?.getAttribute?.('title') || ''];
      if (el?.id && window.CSS?.escape) {
        const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (label) bits.push(label.textContent || '');
      }
      let node = el?.closest?.('label,.form-group,.field,.setting-row,.control-row,.generation-field,.input-row,[data-field],[data-setting],section,details,fieldset,div');
      for (let i = 0; node && i < 5 && !insideSceneDirector(node); i += 1, node = node.parentElement) bits.push(node.id || '', node.className || '', node.getAttribute?.('aria-label') || '', node.getAttribute?.('title') || '', node.dataset?.field || '', node.dataset?.setting || '', node.dataset?.section || '');
      return bits.join(' ').toLowerCase();
    };
    const readNumber = (selectors, meaning) => {
      for (const el of Array.from(document.querySelectorAll(selectors.join(','))).filter(visible)) {
        const ctx = contextOf(el);
        if (ctx.includes('scene-director') || ctx.includes('canvas')) continue;
        if (meaning && !(ctx.includes(meaning) || ctx.includes('generation') || ctx.includes('image') || ctx.includes('build') || ctx.includes('size') || ctx.includes('resolution') || ctx.includes('txt2img'))) continue;
        const raw = String(el.value ?? el.getAttribute?.('value') ?? el.getAttribute?.('aria-valuenow') ?? el.dataset?.value ?? el.textContent ?? '').trim();
        const n = parseInt(raw.replace(/[^0-9]/g, ''), 10);
        if (Number.isFinite(n) && n >= 64 && n <= 8192) return n;
      }
      return null;
    };
    const width = readNumber(['#generation-width','#width','#txt2img-width','#image-width','#neo-width','#neo-generation-width','[name="width"]','[name="generation_width"]','[name="image_width"]','[data-generation-width]','[data-width]','[role="spinbutton"]','[contenteditable="true"]','input','select'], 'width');
    const height = readNumber(['#generation-height','#height','#txt2img-height','#image-height','#neo-height','#neo-generation-height','[name="height"]','[name="generation_height"]','[name="image_height"]','[data-generation-height]','[data-height]','[role="spinbutton"]','[contenteditable="true"]','input','select'], 'height');
    const pair = valid(width, height);
    if (pair) return { ...pair, size_source: 'build-dom-explicit' };
    const sizeSelectors = ['#generation-size','#generation-size-preset','#generation-resolution','#image-size','#image-resolution','#generation-output-size','[name="size"]','[name="size_preset"]','[name="resolution"]','[name="generation_size"]','[name="image_size"]','[data-generation-size]','[data-size-preset]','[data-resolution]','[data-size]'];
    for (const el of Array.from(document.querySelectorAll(sizeSelectors.join(','))).filter(visible)) {
      const parsed = parseSizeText(textOf(el));
      if (parsed) return { ...parsed, size_source: 'build-dom-size-control' };
    }
    const candidates = Array.from(document.querySelectorAll('select,option:checked,input,button,[role="button"],[role="option"],[aria-selected="true"],[aria-pressed="true"],.active,.selected,[data-active="true"],[data-selected="true"],[data-value],[data-size],[data-resolution]')).filter(visible);
    for (const el of candidates) {
      const ctx = contextOf(el);
      const txt = textOf(el);
      const combined = `${ctx} ${txt}`.toLowerCase();
      if (combined.includes('scene director') || combined.includes('regional editor') || combined.includes('preview shell')) continue;
      const hasExplicitSize = /[1-8][0-9]{2,3}\s*[x×]\s*[1-8][0-9]{2,3}/.test(txt);
      const looksBuildSize = combined.includes('build') || combined.includes('generation') || combined.includes('txt2img') || combined.includes('image size') || combined.includes('resolution') || combined.includes('orientation') || combined.includes('aspect') || combined.includes('size');
      if (!looksBuildSize && !hasExplicitSize) continue;
      const parsed = parseSizeText(txt);
      if (parsed) return { ...parsed, size_source: 'build-dom-selected-size' };
    }
    return null;
  }

  function refreshBuildSizeFromDom(source = 'build-dom-sync') {
    const parsed = readLiveBuildSizeFromDom();
    if (!parsed) return getState();
    const current = currentState.build || {};
    if (Number(current.width) === Number(parsed.width) && Number(current.height) === Number(parsed.height) && current.size_source === parsed.size_source) return getState();
    return updateBuild(parsed, source);
  }

  function installBuildSizeBridge() {
    if (typeof document === 'undefined' || window.__neoImageStateBuildSizeBridgeInstalled) return;
    window.__neoImageStateBuildSizeBridgeInstalled = true;
    let scheduled = false;
    const schedule = (source = 'build-dom-event') => {
      if (scheduled) return;
      scheduled = true;
      const run = () => { scheduled = false; refreshBuildSizeFromDom(source); };
      if (window.requestAnimationFrame) window.requestAnimationFrame(run); else window.setTimeout(run, 40);
    };
    const relevant = (target) => {
      const text = String(target?.id || target?.name || target?.className || target?.getAttribute?.('aria-label') || target?.getAttribute?.('title') || target?.textContent || '').toLowerCase();
      return text.includes('width') || text.includes('height') || text.includes('size') || text.includes('resolution') || text.includes('orientation') || text.includes('aspect') || /[1-8][0-9]{2,3}\s*[x×]\s*[1-8][0-9]{2,3}/.test(text);
    };
    ['input', 'change'].forEach(type => document.addEventListener(type, event => { if (relevant(event.target)) schedule(`build-${type}`); }, true));
    document.addEventListener('click', event => { if (relevant(event.target) || relevant(event.target?.closest?.('button,[role="button"],[role="option"],[data-size],[data-resolution],[data-value]'))) window.setTimeout(() => schedule('build-click'), 20); }, true);
    try {
      const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          if (mutation.type === 'attributes' && relevant(mutation.target)) { schedule('build-mutation'); return; }
          if (mutation.type === 'childList') {
            for (const node of Array.from(mutation.addedNodes || [])) if (node.nodeType === 1 && relevant(node)) { schedule('build-dom-added'); return; }
          }
        }
      });
      observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['class','value','aria-selected','aria-pressed','data-selected','data-active','data-value','data-size','data-resolution'] });
    } catch (_) {}
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => schedule('build-dom-ready'), { once: true });
    else window.setTimeout(() => schedule('build-dom-ready'), 50);
    window.setInterval(() => refreshBuildSizeFromDom('build-dom-poll'), 900);
  }

  window.NeoImageState = {
    version: VERSION,
    getState,
    setState,
    setWorkflowMode,
    normalizeWorkflowMode,
    updateBuild,
    updatePrompt,
    updateSource,
    updateModule,
    lockSelectedOutput,
    lockPreviewOutput,
    lockUploadedSource,
    clearOutputSelection,
    resolvePreviewSource,
    validateWorkflowState,
    buildWorkflowPayloadState,
    buildPersistedWorkflowState,
    restoreWorkflowState,
    ingestGenerationPayload,
    getBuildSize,
    readLiveBuildSizeFromDom,
    refreshBuildSizeFromDom,
    subscribe,
    normalize,
  };

  window.validateGenerationWorkflowState = validateWorkflowState;
  installBuildSizeBridge();
  emit({ source: 'init' });
})();

(function () {
  const COMMAND_VERSION = 'image-command-v1';

const RETIRED_PREFIXES = [
  'regional_', 'regionalPrompt',
  'expression_', 'expression_editor_', 'expressionEditor', 'expression_sample_',
  'reference_match_', 'referenceMatch',
  'cleanup_prep_', 'cleanupPrep',
];
const RETIRED_KEYS = new Set([
  'regionalBackendCapabilities','regional_prompt_regions','regional_backend_capabilities','regional_prompt_enabled','regional_prompt',
  'expression_editor_pass','expression_editor_enabled','expression_pass','expression_enabled','expression_editor','expressionEditor','expression_sample',
  'reference_match_enabled','reference_match','referenceMatch','reference_match_shell',
  'cleanup_prep_enabled','cleanup_prep','cleanupPrep',
]);
const RETIRED_MODULE_KEYS = new Set(['cleanup_prep','cleanupPrep','reference_match','referenceMatch','reference_match_shell','expression_editor','expressionEditor','legacy_regional_prompter']);
const RETIRED_PREVIEW_ACTIONS = new Set(['expression','expression_editor','reference_match','reference_match_shell','cleanup_prep','regional','regional_prompt']);
const SURVIVING_REFERENCE_KEYS = new Set(['ipadapter','ipadapter_units','ipadapter_image','ipadapter_image_name','ipadapter_model','ipadapter_weight','scene_director_ipadapter_units','scene_director_identity_units','character_profile','character_profiles']);

function isRetiredKey(key) {
  const text = String(key || '');
  if (SURVIVING_REFERENCE_KEYS.has(text)) return false;
  return RETIRED_KEYS.has(text) || RETIRED_PREFIXES.some((prefix) => text.startsWith(prefix));
}

function scrubRetiredSections(value, removed) {
  if (Array.isArray(value)) return value.map((item) => scrubRetiredSections(item, removed));
  if (!isPlainObject(value)) return clone(value);
  const out = {};
  Object.entries(value).forEach(([key, item]) => {
    if (isRetiredKey(key)) {
      if (removed) removed.push(key);
      return;
    }
    out[key] = scrubRetiredSections(item, removed);
  });
  return out;
}

function scrubModules(modules, removed) {
  if (!isPlainObject(modules)) return {};
  const out = {};
  Object.entries(modules).forEach(([key, value]) => {
    if (RETIRED_MODULE_KEYS.has(key) || isRetiredKey(key)) {
      if (removed) removed.push(`modules.${key}`);
      return;
    }
    out[key] = scrubRetiredSections(value, removed);
  });
  return out;
}

function sanitizeRetiredSections(payload) {
  const removed = [];
  const out = scrubRetiredSections(isPlainObject(payload) ? payload : {}, removed);
  if (isPlainObject(out.modules)) out.modules = scrubModules(out.modules, removed);
  if (isPlainObject(out.image_state) && isPlainObject(out.image_state.modules)) out.image_state.modules = scrubModules(out.image_state.modules, removed);
  const action = out._neo_preview_action || out.preview_action;
  const actionType = String((isPlainObject(action) ? (action.action_type || action.type) : action) || '').trim().toLowerCase();
  if (RETIRED_PREVIEW_ACTIONS.has(actionType)) {
    delete out._neo_preview_action;
    delete out.preview_action;
    removed.push(`preview_action.${actionType}`);
    if (actionType === 'expression' || actionType === 'expression_editor') out.detailer_output_pass = false;
  }
  out._neo_retired_sections_sanitized = true;
  out._neo_retired_sections_version = 'image-retired-sections-v1';
  if (removed.length) out._neo_retired_sections_removed_keys = Array.from(new Set(removed)).slice(0, 80);
  return out;
}

window.NeoImageRetiredSections = {
  version: 'image-retired-sections-v1',
  sanitize: sanitizeRetiredSections,
  isRetiredKey,
};


  function clone(value) {
    if (value == null || typeof value !== 'object') return value;
    try { return structuredClone(value); } catch (_) { return JSON.parse(JSON.stringify(value)); }
  }

  function isPlainObject(value) {
    return !!value && typeof value === 'object' && !Array.isArray(value);
  }

  function inferCommandType(payload, explicitType) {
    const requested = String(explicitType || payload?.command_type || payload?.image_command || '').trim().toLowerCase();
    if (requested) return requested;
    const preview = payload?.preview_action || {};
    const action = String(payload?._neo_preview_action || preview.action_type || preview.type || '').trim().toLowerCase();
    if (action) {
      if (action.includes('detailer') || action.includes('adetailer')) return 'preview_adetailer';
      if (action.includes('upscale')) return 'preview_upscale';
      return 'preview_action';
    }
    const mode = String(payload?.mode || payload?.workflow_type || payload?.refine_mode || '').trim().toLowerCase();
    if (mode === 'supir') return 'supir';
    if (mode === 'upscale' || mode === 'upscale_lab') return 'upscale_lab';
    return 'main_generate';
  }

  function buildImageCommandPayload(commandType, legacyPayload, options) {
    const legacy = sanitizeRetiredSections(isPlainObject(legacyPayload) ? clone(legacyPayload) : {});
    const state = sanitizeRetiredSections(window.NeoImageState?.getState ? window.NeoImageState.getState() : {});
    const command = inferCommandType(legacy, commandType);
    const previewSource = window.NeoImageState?.resolvePreviewSource ? window.NeoImageState.resolvePreviewSource(options?.source || {}) : { locked: false, target: null };
    const source = Object.assign({}, state?.source || {}, isPlainObject(options?.source) ? options.source : {}, {
      locked_source: previewSource.target || (state?.source || {}).locked_source || null,
      explicit_source_type: previewSource.source_type || (state?.source || {}).explicit_source_type || null,
      source_selection_locked: !!previewSource.locked,
    });
    const previewAction = Object.assign({}, isPlainObject(legacy.preview_action) ? legacy.preview_action : {}, isPlainObject(options?.preview_action) ? options.preview_action : {});
    if (previewSource.target && !previewAction.target) previewAction.target = clone(previewSource.target);
    if (legacy.generationPreviewActionTarget && !previewAction.target) previewAction.target = clone(legacy.generationPreviewActionTarget);
    const modules = scrubModules(state?.modules || {}, []);
    if (isPlainObject(legacy.dynamic_thresholding) && !isPlainObject(modules.dynamic_thresholding)) {
      modules.dynamic_thresholding = clone(legacy.dynamic_thresholding);
    }
    return sanitizeRetiredSections({
      version: COMMAND_VERSION,
      command_type: command,
      image_state: clone(state || {}),
      build: clone(state?.build || {}),
      source,
      settings: sanitizeRetiredSections(clone(legacy)),
      modules,
      preview_action: previewAction,
      lineage: isPlainObject(options?.lineage) ? clone(options.lineage) : {},
      legacy_payload: sanitizeRetiredSections(clone(legacy)),
      meta: {
        stage: 'stage6_retired_sections_safe_removal',
        legacy_compatible: true,
        created_at: new Date().toISOString(),
        ...(isPlainObject(options?.meta) ? options.meta : {}),
      },
    });
  }

  function wrapSettingsJson(settings, commandType, options) {
    let payload = settings;
    if (typeof payload === 'string') {
      try { payload = JSON.parse(payload || '{}'); } catch (_) { payload = {}; }
    }
    return JSON.stringify(buildImageCommandPayload(commandType, payload, options || {}));
  }

  window.NeoImagePayloads = {
    version: COMMAND_VERSION,
    inferCommandType,
    buildImageCommandPayload,
    wrapSettingsJson,
  };
})();
