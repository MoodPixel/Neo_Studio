function getGenerationRegionalPaintSoftness() {
  return Math.max(0, Math.min(48, Number($('generation-regional-paint-softness')?.value || 8) || 0));
}

function buildGenerationRegionalSoftenedCanvas(sourceCanvas) {
  if (!sourceCanvas) return null;
  const softness = getGenerationRegionalPaintSoftness();
  if (!(softness > 0)) return sourceCanvas;
  const softened = document.createElement('canvas');
  softened.width = sourceCanvas.width;
  softened.height = sourceCanvas.height;
  const ctx = softened.getContext('2d');
  if (!ctx) return sourceCanvas;
  ctx.clearRect(0, 0, softened.width, softened.height);
  ctx.filter = `blur(${softness}px)`;
  ctx.drawImage(sourceCanvas, 0, 0, softened.width, softened.height);
  ctx.filter = 'none';
  return softened;
}

function getGenerationRegionalDisplayMode() {
  const raw = ($('generation-regional-display-mode')?.value || 'auto').toLowerCase();
  if (raw === 'boxes' || raw === 'masks') return raw;
  return 'auto';
}

function getGenerationRegionalResolvedDisplayMode() {
  const selected = getGenerationRegionalDisplayMode();
  if (selected !== 'auto') return selected;
  const composerMode = getGenerationRegionalComposerMode();
  const hasMaskRegion = composerMode === 'advanced' && generationRegionalIndices.some(index => {
    const enabled = !!$(`generation-regional-r${index}-enabled`)?.checked;
    const maskSource = $(`generation-regional-r${index}-mask-source`)?.value || 'rect';
    return enabled && maskSource === 'mask_image';
  });
  return hasMaskRegion ? 'masks' : 'boxes';
}

function getGenerationRegionalCount() {
  const raw = Number($('generation-regional-count')?.value || 3);
  return Math.max(0, Math.min(5, Number.isFinite(raw) ? raw : 3));
}

function setGenerationRegionalCount(count, { silent=false } = {}) {
  const safeCount = Math.max(0, Math.min(5, Number.isFinite(Number(count)) ? Number(count) : 3));
  if ($('generation-regional-count')) $('generation-regional-count').value = String(safeCount);
  if (generationRegionalCanvasState.activeRegion > safeCount) generationRegionalCanvasState.activeRegion = safeCount;
  if (generationRegionalPaintState.regionIndex > safeCount) generationRegionalPaintState.regionIndex = safeCount;
  if (safeCount === 0) { generationRegionalCanvasState.activeRegion = 0; generationRegionalPaintState.regionIndex = 0; }
  applyGenerationRegionalCountLayout(safeCount, { silent });
}

function stepGenerationRegionalCount(delta) {
  const next = Math.max(0, Math.min(5, getGenerationRegionalCount() + Number(delta || 0)));
  if (next === getGenerationRegionalCount()) {
    setStatus('generation-status', next >= 5 ? 'Regional Composer is already at the 5-region limit.' : 'Regional Composer already uses 0 regions.', 'info');
    return;
  }
  setGenerationRegionalCount(next);
}

function applyGenerationRegionalCountLayout(count, { silent=false } = {}) {
  const safeCount = Math.max(0, Math.min(5, Number.isFinite(Number(count)) ? Number(count) : 3));
  const profile = $('generation-regional-profile')?.value || 'custom';
  const vertical = profile === 'top_middle_bottom';
  generationRegionalIndices.forEach(index => {
    if ($(`generation-regional-r${index}-enabled`)) $(`generation-regional-r${index}-enabled`).checked = index <= safeCount;
    if (index > safeCount) return;
    if (vertical) {
      const h = 100 / safeCount;
      writeGenerationRegionalRect(index, { x:0, y:(index - 1) * h, w:100, h });
    } else {
      const w = 100 / safeCount;
      writeGenerationRegionalRect(index, { x:(index - 1) * w, y:0, w, h:100 });
    }
  });
  syncGenerationRegionalPromptUI();
  if (!silent) setStatus('generation-status', safeCount === 0 ? 'Regional Composer now uses 0 regions.' : `Regional Composer now uses ${safeCount} region slot${safeCount === 1 ? '' : 's'}.`);
  scheduleGenerationDraftSave();
  scheduleGenerationSectionBadgeRefresh();
}


function getGenerationRegionalPaintCanvas(index, create=false) {
  const current = generationRegionalPaintState.canvasByRegion[index];
  const { width, height } = getGenerationRegionalCanvasAspect();
  if (current && current.width === width && current.height === height) return current;
  if (!create) return null;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (current && ctx) ctx.drawImage(current, 0, 0, width, height);
  generationRegionalPaintState.canvasByRegion[index] = canvas;
  return canvas;
}

function renderGenerationRegionalPaintOverlay() {
  const overlay = $('generation-regional-paint-overlay');
  const stage = $('generation-regional-canvas-stage');
  if (!(overlay instanceof HTMLCanvasElement) || !stage) return;
  const rect = stage.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width || stage.clientWidth || 1));
  const height = Math.max(1, Math.round(rect.height || stage.clientHeight || 1));
  if (overlay.width !== width) overlay.width = width;
  if (overlay.height !== height) overlay.height = height;
  const ctx = overlay.getContext('2d');
  if (!ctx) return;
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  const index = generationRegionalPaintState.regionIndex || 1;
  const paintCanvas = buildGenerationRegionalSoftenedCanvas(getGenerationRegionalPaintCanvas(index, false));
  if (!paintCanvas) return;
  ctx.save();
  ctx.globalAlpha = 0.42;
  ctx.drawImage(paintCanvas, 0, 0, overlay.width, overlay.height);
  ctx.globalCompositeOperation = 'source-atop';
  ctx.fillStyle = index === 2 ? 'rgba(84,231,187,0.95)' : (index === 3 ? 'rgba(192,132,252,0.95)' : 'rgba(86,152,255,0.95)');
  ctx.fillRect(0, 0, overlay.width, overlay.height);
  ctx.restore();
}

function setGenerationRegionalActiveRegion(index, { render=true } = {}) {
  const safe = Math.max(0, Math.min(5, Number(index) || 0));
  generationRegionalCanvasState.activeRegion = safe;
  generationRegionalPaintState.regionIndex = safe;
  const label = safe > 0 ? (trim($(`generation-regional-r${safe}-label`)?.value || '') || `Region ${safe}`) : 'No active region';
  if ($('generation-regional-active-region')) $('generation-regional-active-region').value = label;
  if (render) renderGenerationRegionalCanvas();
}

function drawGenerationRegionalPainterStroke(event, { firstPoint=false } = {}) {
  if (!generationRegionalPaintState.drawing) return;
  const stage = $('generation-regional-canvas-stage');
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  const index = generationRegionalPaintState.regionIndex || 1;
  const canvas = getGenerationRegionalPaintCanvas(index, true);
  const ctx = canvas?.getContext('2d');
  if (!canvas || !ctx) return;
  const x = ((event.clientX - rect.left) / Math.max(1, rect.width)) * canvas.width;
  const y = ((event.clientY - rect.top) / Math.max(1, rect.height)) * canvas.height;
  const brushPx = (getGenerationRegionalPainterBrush() / Math.max(1, rect.width)) * canvas.width;
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(2, brushPx);
  if (generationRegionalPaintState.mode === 'erase') {
    ctx.globalCompositeOperation = 'destination-out';
    ctx.strokeStyle = 'rgba(0,0,0,1)';
  } else {
    ctx.globalCompositeOperation = 'source-over';
    ctx.strokeStyle = 'rgba(255,255,255,1)';
  }
  ctx.beginPath();
  if (firstPoint || generationRegionalPaintState.lastX == null || generationRegionalPaintState.lastY == null) {
    ctx.moveTo(x, y);
    ctx.lineTo(x + 0.01, y + 0.01);
  } else {
    ctx.moveTo(generationRegionalPaintState.lastX, generationRegionalPaintState.lastY);
    ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.restore();
  generationRegionalPaintState.lastX = x;
  generationRegionalPaintState.lastY = y;
  renderGenerationRegionalPaintOverlay();
}

function beginGenerationRegionalPainter(event) {
  if (getGenerationRegionalComposerMode() !== 'advanced') return;
  const mode = getGenerationRegionalPainterMode();
  if (mode === 'off') return;
  const paintRegion = generationRegionalPaintState.regionIndex || generationRegionalCanvasState.activeRegion || 1;
  if (paintRegion > 0 && !!$(`generation-regional-r${paintRegion}-lock`)?.checked) {
    setStatus('generation-status', `Region ${paintRegion} is locked. Unlock it before painting.`, 'warn');
    return;
  }
  generationRegionalPaintState.mode = mode;
  generationRegionalPaintState.brush = getGenerationRegionalPainterBrush();
  generationRegionalPaintState.drawing = true;
  generationRegionalPaintState.pointerId = event.pointerId;
  generationRegionalPaintState.lastX = null;
  generationRegionalPaintState.lastY = null;
  $('generation-regional-canvas-stage')?.classList.add('is-painting');
  event.preventDefault();
  drawGenerationRegionalPainterStroke(event, { firstPoint:true });
}

function handleGenerationRegionalPainterMove(event) {
  if (!generationRegionalPaintState.drawing) return;
  drawGenerationRegionalPainterStroke(event);
}

function endGenerationRegionalPainter() {
  if (!generationRegionalPaintState.drawing) return;
  generationRegionalPaintState.drawing = false;
  generationRegionalPaintState.pointerId = null;
  generationRegionalPaintState.lastX = null;
  generationRegionalPaintState.lastY = null;
  $('generation-regional-canvas-stage')?.classList.remove('is-painting');
  renderGenerationRegionalPaintOverlay();
}

function clearGenerationRegionalPaintMask() {
  const index = generationRegionalPaintState.regionIndex || generationRegionalCanvasState.activeRegion || 1;
  const canvas = getGenerationRegionalPaintCanvas(index, false);
  const ctx = canvas?.getContext('2d');
  if (canvas && ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
  renderGenerationRegionalPaintOverlay();
  setStatus('generation-status', `Cleared the painted mask draft for Region ${index}.`);
}

async function applyGenerationRegionalPaintMask() {
  const index = generationRegionalPaintState.regionIndex || generationRegionalCanvasState.activeRegion || 1;
  const canvas = buildGenerationRegionalSoftenedCanvas(getGenerationRegionalPaintCanvas(index, false));
  if (!canvas) {
    setStatus('generation-status', 'Paint a mask on the stage first.', 'warn');
    return;
  }
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  if (!blob) {
    setStatus('generation-status', 'Could not turn the painted mask into a PNG file.', 'error');
    return;
  }
  const file = new File([blob], `regional_mask_painted_${index}.png`, { type:'image/png' });
  assignFileToInput(`generation-regional-r${index}-mask-image`, file);
  if ($('generation-regional-composer-mode')) $('generation-regional-composer-mode').value = 'advanced';
  if ($(`generation-regional-r${index}-mask-source`)) $(`generation-regional-r${index}-mask-source`).value = 'mask_image';
  if ($(`generation-regional-r${index}-mask-channel`)) $(`generation-regional-r${index}-mask-channel`).value = 'alpha';
  await refreshGenerationRegionalMaskPreview(index);
  markGenerationRegionalPromptCustom();
  syncGenerationRegionalPromptUI();
  scheduleGenerationDraftSave();
  scheduleGenerationSectionBadgeRefresh();
  setStatus('generation-status', `Painted mask applied to Region ${index} as an alpha-channel mask image.`, 'success');
}

function beginGenerationRegionalCanvasDrag(index, mode, event) {
  const stage = $('generation-regional-canvas-stage');
  if (!stage) return;
  const composerMode = getGenerationRegionalComposerMode();
  const maskSource = composerMode === 'advanced' ? ($(`generation-regional-r${index}-mask-source`)?.value || 'rect') : 'rect';
  if (!!$(`generation-regional-r${index}-lock`)?.checked) return;
  if (maskSource !== 'rect') return;
  const rect = stage.getBoundingClientRect();
  const x = Number($(`generation-regional-r${index}-x`)?.value || 0);
  const y = Number($(`generation-regional-r${index}-y`)?.value || 0);
  const w = Number($(`generation-regional-r${index}-w`)?.value || 34);
  const h = Number($(`generation-regional-r${index}-h`)?.value || 100);
  generationRegionalCanvasState = {
    activeRegion: index,
    dragMode: mode,
    regionIndex: index,
    pointerId: event.pointerId,
    startPointerX: event.clientX,
    startPointerY: event.clientY,
    startX: x,
    startY: y,
    startW: w,
    startH: h,
    stageLeft: rect.left,
    stageTop: rect.top,
    stageWidth: Math.max(1, rect.width),
    stageHeight: Math.max(1, rect.height),
  };
  try { event.target?.setPointerCapture?.(event.pointerId); } catch (_) {}
  event.preventDefault();
  renderGenerationRegionalCanvas();
}

function handleGenerationRegionalCanvasMove(event) {
  if (!generationRegionalCanvasState.dragMode || !generationRegionalCanvasState.regionIndex) return;
  const s = generationRegionalCanvasState;
  const dxPct = ((event.clientX - s.startPointerX) / Math.max(1, s.stageWidth)) * 100;
  const dyPct = ((event.clientY - s.startPointerY) / Math.max(1, s.stageHeight)) * 100;
  let x = s.startX;
  let y = s.startY;
  let w = s.startW;
  let h = s.startH;
  if (s.dragMode === 'move') {
    x = Math.max(0, Math.min(100 - w, s.startX + dxPct));
    y = Math.max(0, Math.min(100 - h, s.startY + dyPct));
  } else if (s.dragMode === 'resize') {
    w = Math.max(4, Math.min(100 - x, s.startW + dxPct));
    h = Math.max(4, Math.min(100 - y, s.startH + dyPct));
  }
  writeGenerationRegionalRect(s.regionIndex, { x, y, w, h });
  markGenerationRegionalPromptCustom();
  scheduleGenerationDraftSave();
  scheduleGenerationSectionBadgeRefresh();
  renderGenerationRegionalCanvas();
}

function endGenerationRegionalCanvasMove() {
  if (!generationRegionalCanvasState.dragMode) return;
  generationRegionalCanvasState.dragMode = '';
  generationRegionalCanvasState.pointerId = null;
  renderGenerationRegionalCanvas();
}

function renderGenerationRegionalCanvas() {
  const stage = $('generation-regional-canvas-stage');
  const empty = $('generation-regional-canvas-empty');
  const summary = $('generation-regional-canvas-summary');
  if (!stage) return;
  const regionalSnapshot = getGenerationRegionalEffectiveStateSnapshot();
  const enabled = regionalSnapshot.enabledRoot;
  const composerMode = regionalSnapshot.composerMode;
  const painterMode = getGenerationRegionalPainterMode();
  const regionCount = regionalSnapshot.regionCount;
  const visualMode = getGenerationRegionalResolvedDisplayMode();
  const overlapMode = (($('generation-regional-overlap-mode')?.value || 'blend') === 'priority') ? 'priority' : 'blend';
  const aspect = getGenerationRegionalCanvasAspect();
  stage.style.aspectRatio = `${aspect.width} / ${aspect.height}`;
  let maskPreviewCount = 0;
  if (summary) summary.textContent = `${aspect.width} × ${aspect.height} canvas · ${composerMode === 'advanced' ? 'Advanced' : 'Basic'} editor · ${regionCount} slots · ${visualMode === 'masks' ? 'Mask view' : 'Box view'}${composerMode === 'advanced' ? ` · ${overlapMode === 'priority' ? 'Priority overlap' : 'Blend overlap'}` : ''}${composerMode === 'advanced' && painterMode !== 'off' ? ` · ${painterMode} · soft ${getGenerationRegionalPaintSoftness()}px` : ''}`;
  if (empty) empty.classList.toggle('is-hidden', enabled);
  for (let index = 1; index <= 5; index += 1) {
    let overlay = stage.querySelector(`.generation-regional-canvas-mask-overlay[data-region-index="${index}"]`);
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'generation-regional-canvas-mask-overlay is-hidden';
      overlay.dataset.regionIndex = String(index);
      overlay.innerHTML = '<img class="generation-regional-canvas-mask-image" alt="Mask preview" /><div class="generation-regional-canvas-mask-label"></div>';
      stage.appendChild(overlay);
    }
    let node = stage.querySelector(`.generation-regional-canvas-region[data-region-index="${index}"]`);
    if (!node) {
      node = document.createElement('div');
      node.className = 'generation-regional-canvas-region';
      node.dataset.regionIndex = String(index);
      node.innerHTML = '<div class="generation-regional-canvas-region-header"><span class="generation-regional-canvas-label"></span><span class="generation-regional-canvas-meta"></span></div><div class="generation-regional-canvas-region-body"></div><div class="generation-regional-canvas-resize" title="Resize region"></div>';
      stage.appendChild(node);
      const beginMove = (event) => {
        setGenerationRegionalActiveRegion(index, { render:false });
        if (getGenerationRegionalComposerMode() === 'advanced' && getGenerationRegionalPainterMode() !== 'off') return;
        if ((event.target instanceof HTMLElement) && event.target.classList.contains('generation-regional-canvas-resize')) return;
        event.stopPropagation();
        beginGenerationRegionalCanvasDrag(index, 'move', event);
      };
      node.addEventListener('pointerdown', beginMove);
      node.addEventListener('mousedown', beginMove);
      const resizeNode = node.querySelector('.generation-regional-canvas-resize');
      const beginResize = (event) => {
        setGenerationRegionalActiveRegion(index, { render:false });
        if (getGenerationRegionalComposerMode() === 'advanced' && getGenerationRegionalPainterMode() !== 'off') return;
        event.stopPropagation();
        beginGenerationRegionalCanvasDrag(index, 'resize', event);
      };
      resizeNode?.addEventListener('pointerdown', beginResize);
      resizeNode?.addEventListener('mousedown', beginResize);
    }
    const regionEnabled = index <= regionCount && enabled && !!$(`generation-regional-r${index}-enabled`)?.checked;
    const maskSource = composerMode === 'advanced' ? ($(`generation-regional-r${index}-mask-source`)?.value || 'rect') : 'rect';
    const regionRuntime = regionalSnapshot.regions.find(region => region.index === index) || { effectiveEnabled:false, locked:false, enabled:false, muted:false, solo:false };
    const maskPreview = generationRegionalMaskPreviewCache[index];
    if (overlay) {
      const hasMaskPreview = enabled && regionRuntime.effectiveEnabled && visualMode === 'masks' && maskSource === 'mask_image' && !!maskPreview?.previewUrl;
      overlay.classList.toggle('is-hidden', !hasMaskPreview);
      overlay.querySelector('.generation-regional-canvas-mask-image')?.setAttribute('src', hasMaskPreview ? maskPreview.previewUrl : '');
      const overlayLabel = overlay.querySelector('.generation-regional-canvas-mask-label');
      if (overlayLabel) overlayLabel.textContent = hasMaskPreview ? (trim($(`generation-regional-r${index}-label`)?.value || '') || `Region ${index}`) : '';
      if (hasMaskPreview) maskPreviewCount += 1;
    }
    const x = Math.max(0, Math.min(100, Number($(`generation-regional-r${index}-x`)?.value || 0)));
    const y = Math.max(0, Math.min(100, Number($(`generation-regional-r${index}-y`)?.value || 0)));
    const w = Math.max(4, Math.min(100 - x, Number($(`generation-regional-r${index}-w`)?.value || 34)));
    const h = Math.max(4, Math.min(100 - y, Number($(`generation-regional-r${index}-h`)?.value || 100)));
    node.style.left = `${x}%`;
    node.style.top = `${y}%`;
    node.style.width = `${w}%`;
    node.style.height = `${h}%`;
    node.classList.toggle('is-hidden', !regionRuntime.effectiveEnabled || !enabled || visualMode === 'masks' || maskSource === 'mask_image');
    node.classList.toggle('is-disabled', !regionRuntime.effectiveEnabled);
    node.classList.toggle('is-selected', generationRegionalCanvasState.activeRegion === index);
    node.classList.toggle('is-mask-only', maskSource === 'mask_image');
    node.style.pointerEvents = regionRuntime.locked || (composerMode === 'advanced' && painterMode !== 'off') || maskSource === 'mask_image' ? 'none' : 'auto';
    const priority = Math.max(1, Math.min(3, Number($(`generation-regional-r${index}-priority`)?.value || index) || index));
    if (overlay) overlay.style.zIndex = String(10 + (4 - priority));
    node.style.zIndex = String(20 + (4 - priority));
    const label = trim($(`generation-regional-r${index}-label`)?.value || '') || `Region ${index}`;
    const pos = trim($(`generation-regional-r${index}-prompt`)?.value || '');
    const neg = trim($(`generation-regional-r${index}-negative-prompt`)?.value || '');
    const bodyText = maskSource === 'mask_image'
      ? 'Mask image region · box preview hidden from payload'
      : `${Math.round(x)} / ${Math.round(y)} · ${Math.round(w)} × ${Math.round(h)}%`;
    const meta = [pos ? 'P' : '', neg ? 'N' : '', maskSource === 'mask_image' ? 'Mask' : 'Rect', regionRuntime.solo ? 'Solo' : '', regionRuntime.muted ? 'Mute' : '', regionRuntime.locked ? 'Lock' : ''].filter(Boolean).join(' · ');
    const labelNode = node.querySelector('.generation-regional-canvas-label');
    const metaNode = node.querySelector('.generation-regional-canvas-meta');
    const bodyNode = node.querySelector('.generation-regional-canvas-region-body');
    if (labelNode) labelNode.textContent = label;
    if (metaNode) metaNode.textContent = meta;
    if (bodyNode) bodyNode.textContent = bodyText;
    const resizeHandle = node.querySelector('.generation-regional-canvas-resize');
    if (resizeHandle) resizeHandle.classList.toggle('is-hidden', maskSource === 'mask_image' || (composerMode === 'advanced' && painterMode !== 'off'));
  }
  if (summary && maskPreviewCount) summary.textContent += ` · ${maskPreviewCount} mask overlay${maskPreviewCount === 1 ? '' : 's'}`;
  setGenerationRegionalActiveRegion(generationRegionalCanvasState.activeRegion || generationRegionalPaintState.regionIndex || 1, { render:false });
  renderGenerationRegionalPaintOverlay();
}


function syncGenerationRegionalPromptUI() {
  const enabled = String($('generation-regional-enabled')?.value || 'false') === 'true';
  const composerMode = getGenerationRegionalComposerMode();
  const regionCount = getGenerationRegionalCount();
  const contextSupport = getGenerationRegionalContextSupport();
  const backendSelect = $('generation-regional-backend-mode');
  if (backendSelect) {
    const denseOption = backendSelect.querySelector('option[value="dense_diffusion"]');
    if (denseOption) {
      denseOption.disabled = true;
      denseOption.hidden = true;
      if (backendSelect.value === 'dense_diffusion') backendSelect.value = 'auto';
    }
    const nodeOption = backendSelect.querySelector('option[value="node"]');
    if (nodeOption) {
      const nodeReady = !!(generationCatalogState?.regional_backend_capabilities?.node?.available);
      nodeOption.disabled = !nodeReady;
      nodeOption.hidden = false;
      nodeOption.textContent = nodeReady ? 'Node backend (recommended)' : 'Node backend (unavailable)';
      if (!nodeReady && backendSelect.value === 'node') backendSelect.value = 'native';
    }
  }
  const backendMode = getGenerationRegionalBackendMode();
  const backendRuntime = getGenerationRegionalBackendRuntime(backendMode);
  if ($('generation-regional-mode-note')) $('generation-regional-mode-note').value = backendRuntime.note;
  const promotion = backendRuntime.promotion || { promoted:false, verifiedCaseCount:0, minimumVerifiedCaseCount:0, acceptanceMet:false, notes:[] };
  document.querySelectorAll('[data-accordion-id="generation-regional-prompt-settings"] .generation-regional-advanced').forEach(el => {
    el.classList.toggle('is-hidden', composerMode !== 'advanced');
  });
  document.querySelectorAll('.generation-regional-row').forEach(row => {
    const indexNumber = Number(row.getAttribute('data-region-index') || '1');
    row.classList.toggle('is-hidden', indexNumber > regionCount);
    row.classList.toggle('is-disabled', !enabled);
    row.classList.toggle('generation-regional-basic-mode', composerMode !== 'advanced');
    row.querySelectorAll('textarea, input[type="number"], input[type="checkbox"], input[type="text"], select').forEach(control => {
      if (!(control instanceof HTMLInputElement) || control.type !== 'file') control.disabled = !enabled;
    });
    const index = row.getAttribute('data-region-index') || '1';
    const rawMaskSource = $(`generation-regional-r${index}-mask-source`)?.value || 'rect';
    const maskSource = composerMode === 'advanced' ? rawMaskSource : 'rect';
    const rectWrap = $(`generation-regional-r${index}-rect-wrap`);
    const fileWrap = $(`generation-regional-r${index}-mask-file-wrap`);
    const channelWrap = $(`generation-regional-r${index}-mask-channel-wrap`);
    rectWrap?.classList.toggle('is-hidden', maskSource !== 'rect');
    fileWrap?.classList.toggle('is-hidden', composerMode !== 'advanced' || maskSource !== 'mask_image');
    channelWrap?.classList.toggle('is-hidden', composerMode !== 'advanced' || maskSource !== 'mask_image');
    const fileInput = $(`generation-regional-r${index}-mask-image`);
    if (fileInput) fileInput.disabled = !enabled || composerMode !== 'advanced' || maskSource !== 'mask_image';
  });
  const regionalSnapshot = getGenerationRegionalEffectiveStateSnapshot();
  const activeIndices = regionalSnapshot.effectiveIndices.filter(index => (trim($(`generation-regional-r${index}-prompt`)?.value || '') || trim($(`generation-regional-r${index}-negative-prompt`)?.value || '')));
  const imageMaskCount = composerMode === 'advanced' ? activeIndices.filter(index => ($(`generation-regional-r${index}-mask-source`)?.value || 'rect') === 'mask_image').length : 0;
  const softEdgeCount = composerMode === 'advanced' ? activeIndices.filter(index => Number($(`generation-regional-r${index}-falloff`)?.value || 0) > 0).length : 0;
  const profileLabel = $('generation-regional-profile')?.selectedOptions?.[0]?.textContent?.trim() || 'Custom';
  const namedActive = generationRegionalIndices.map(index => trim($(`generation-regional-r${index}-label`)?.value || '')).filter(Boolean);
  const parts = [enabled ? `${activeIndices.length} active region${activeIndices.length === 1 ? '' : 's'}` : 'Regional Composer is off'];
  if (enabled) parts.push(profileLabel);
  if (enabled && composerMode === 'advanced' && regionalSnapshot.hasSolo) parts.push('Solo focus');
  if (enabled) parts.push(`${regionCount} region slot${regionCount === 1 ? '' : 's'}`);
  if (enabled) parts.push(composerMode === 'advanced' ? 'Advanced' : 'Basic');
  if (enabled) parts.push(backendRuntime.label);
  if (enabled && composerMode === 'advanced') parts.push((($('generation-regional-overlap-mode')?.value || 'blend') === 'priority') ? 'Priority overlap' : 'Blend overlap');
  if (enabled && composerMode === 'advanced' && namedActive.length) parts.push(namedActive.join(', '));
  if (enabled && composerMode === 'advanced' && imageMaskCount) parts.push(`${imageMaskCount} mask image${imageMaskCount === 1 ? '' : 's'}`);
  if (enabled && composerMode === 'advanced' && softEdgeCount) parts.push(`${softEdgeCount} soft edge${softEdgeCount === 1 ? '' : 's'}`);
  if (enabled) parts.push('Txt2img-first');
  if ($('generation-regional-summary')) $('generation-regional-summary').textContent = parts.join(' · ');
  const debugBits = [];
  if (!enabled) debugBits.push('Regional Composer is off.');
  else {
    const soloIndices = regionalSnapshot.regions.filter(region => region.solo && region.enabled).map(region => `R${region.index}`);
    const muteIndices = regionalSnapshot.regions.filter(region => region.muted && region.enabled).map(region => `R${region.index}`);
    const lockIndices = regionalSnapshot.regions.filter(region => region.locked && region.enabled).map(region => `R${region.index}`);
    debugBits.push(`Effective: ${regionalSnapshot.effectiveIndices.length ? regionalSnapshot.effectiveIndices.map(index => `R${index}`).join(', ') : 'none'}`);
    debugBits.push(`Display: ${getGenerationRegionalResolvedDisplayMode() === 'masks' ? 'Masks' : 'Boxes'}`);
    debugBits.push(`Requested backend: ${getGenerationRegionalBackendLabel(getGenerationRegionalBackendMode())}`);
    debugBits.push(`Actual backend: ${backendRuntime.actual === 'node' ? 'Node backend' : (backendRuntime.actual === 'dense_diffusion' ? 'Dense Diffusion' : 'Native')}`);
    debugBits.push(`Status: ${backendRuntime.status}`);
    debugBits.push(`Promotion: ${promotion.promoted ? 'promoted' : 'not promoted'} (${promotion.verifiedCaseCount}/${promotion.minimumVerifiedCaseCount})`);
    debugBits.push(`Family/mode: ${contextSupport.familyLabel} · ${contextSupport.modeLabel}`);
    if (backendRuntime.fallback) debugBits.push(`Fallback: ${backendRuntime.fallback}`);
    if (soloIndices.length) debugBits.push(`Solo: ${soloIndices.join(', ')}`);
    if (muteIndices.length) debugBits.push(`Mute: ${muteIndices.join(', ')}`);
    if (lockIndices.length) debugBits.push(`Lock: ${lockIndices.join(', ')}`);
  }
  if ($('generation-regional-debug')) $('generation-regional-debug').textContent = debugBits.join(' · ');
  renderGenerationRegionalCanvas();
}

function applyGenerationRegionalPromptProfile(key, { silent=false } = {}) {
  const profile = generationRegionalPromptProfiles[key];
  if (!profile) return;
  if ($('generation-regional-profile')) $('generation-regional-profile').value = key;
  profile.forEach((item, idx) => {
    const n = idx + 1;
    if ($(`generation-regional-r${n}-enabled`)) $(`generation-regional-r${n}-enabled`).checked = !!item.enabled;
    if ($(`generation-regional-r${n}-x`)) $(`generation-regional-r${n}-x`).value = item.x;
    if ($(`generation-regional-r${n}-y`)) $(`generation-regional-r${n}-y`).value = item.y;
    if ($(`generation-regional-r${n}-w`)) $(`generation-regional-r${n}-w`).value = item.w;
    if ($(`generation-regional-r${n}-h`)) $(`generation-regional-r${n}-h`).value = item.h;
    if ($(`generation-regional-r${n}-positive-strength`)) $(`generation-regional-r${n}-positive-strength`).value = item.positive_strength || item.strength || '1.0';
    if ($(`generation-regional-r${n}-negative-strength`)) $(`generation-regional-r${n}-negative-strength`).value = item.negative_strength || item.strength || '1.0';
  });
  syncGenerationRegionalPromptUI();
  if (!silent) setStatus('generation-status', `Regional Composer layout loaded: ${$('generation-regional-profile')?.selectedOptions?.[0]?.textContent?.trim() || key}.`, 'success');
  scheduleGenerationDraftSave();
}

function markGenerationRegionalPromptCustom() {
  if ($('generation-regional-profile')) $('generation-regional-profile').value = 'custom';
  syncGenerationRegionalPromptUI();
}


function bindGenerationRegionalDynamicListeners() {
  generationRegionalIndices.forEach(index => {
    const markCustom = () => {
      markGenerationRegionalPromptCustom();
      scheduleGenerationDraftSave();
      scheduleGenerationSectionBadgeRefresh();
    };
    [
      `generation-regional-r${index}-enabled`,
      `generation-regional-r${index}-solo`,
      `generation-regional-r${index}-mute`,
      `generation-regional-r${index}-lock`,
      `generation-regional-r${index}-label`,
      `generation-regional-r${index}-prompt`,
      `generation-regional-r${index}-negative-prompt`,
      `generation-regional-r${index}-priority`,
      `generation-regional-r${index}-positive-strength`,
      `generation-regional-r${index}-negative-strength`,
      `generation-regional-r${index}-falloff`,
      `generation-regional-r${index}-x`,
      `generation-regional-r${index}-y`,
      `generation-regional-r${index}-w`,
      `generation-regional-r${index}-h`,
    ].forEach(id => {
      const el = $(id);
      if (!el || el.dataset.neoRegionalBound === '1') return;
      el.addEventListener(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', () => {
        if (id.endsWith('-enabled') && !el.checked && generationRegionalCanvasState.activeRegion === index) {
          const fallback = generationRegionalIndices.find(candidate => candidate <= getGenerationRegionalCount() && candidate !== index && !!$(`generation-regional-r${candidate}-enabled`)?.checked) || (getGenerationRegionalCount() > 0 ? 1 : 0);
          generationRegionalCanvasState.activeRegion = fallback;
        }
        markCustom();
      });
      el.dataset.neoRegionalBound = '1';
    });

    const maskSourceEl = $(`generation-regional-r${index}-mask-source`);
    if (maskSourceEl && maskSourceEl.dataset.neoRegionalBound !== '1') {
      maskSourceEl.addEventListener('change', () => {
        setGenerationRegionalActiveRegion(index, { render:false });
        if (maskSourceEl.value === 'mask_image' && $(`generation-regional-r${index}-mask-image`)?.files?.[0]) {
          refreshGenerationRegionalMaskPreview(index).catch(() => renderGenerationRegionalCanvas());
        } else {
          if (maskSourceEl.value !== 'mask_image') revokeGenerationRegionalMaskPreview(index);
          renderGenerationRegionalCanvas();
        }
        markCustom();
      });
      maskSourceEl.dataset.neoRegionalBound = '1';
    }

    const maskChannelEl = $(`generation-regional-r${index}-mask-channel`);
    if (maskChannelEl && maskChannelEl.dataset.neoRegionalBound !== '1') {
      maskChannelEl.addEventListener('change', () => {
        setGenerationRegionalActiveRegion(index, { render:false });
        refreshGenerationRegionalMaskPreview(index).catch(() => renderGenerationRegionalCanvas());
        markCustom();
      });
      maskChannelEl.dataset.neoRegionalBound = '1';
    }

    const maskImageEl = $(`generation-regional-r${index}-mask-image`);
    if (maskImageEl && maskImageEl.dataset.neoRegionalBound !== '1') {
      maskImageEl.addEventListener('change', () => {
        setGenerationRegionalActiveRegion(index, { render:false });
        refreshGenerationRegionalMaskPreview(index).catch(() => renderGenerationRegionalCanvas());
        markCustom();
      });
      maskImageEl.dataset.neoRegionalBound = '1';
    }
  });
}

function getGenerationRegionalRegionFlags(index, context=null) {
  const enabledRoot = context?.enabledRoot ?? (String($('generation-regional-enabled')?.value || 'false') === 'true');
  const composerMode = context?.composerMode ?? getGenerationRegionalComposerMode();
  const regionCount = context?.regionCount ?? getGenerationRegionalCount();
  const withinCount = index <= regionCount;
  const checked = !!$(`generation-regional-r${index}-enabled`)?.checked;
  const solo = composerMode === 'advanced' && !!$(`generation-regional-r${index}-solo`)?.checked;
  const muted = composerMode === 'advanced' && !!$(`generation-regional-r${index}-mute`)?.checked;
  const locked = composerMode === 'advanced' && !!$(`generation-regional-r${index}-lock`)?.checked;
  return { withinCount, checked, solo, muted, locked, enabled: enabledRoot && withinCount && checked };
}

function getGenerationRegionalEffectiveStateSnapshot() {
  const enabledRoot = String($('generation-regional-enabled')?.value || 'false') === 'true';
  const composerMode = getGenerationRegionalComposerMode();
  const regionCount = getGenerationRegionalCount();
  const rawRegions = generationRegionalIndices.map(index => ({ index, ...getGenerationRegionalRegionFlags(index, { enabledRoot, composerMode, regionCount }) }));
  const hasSolo = composerMode === 'advanced' && rawRegions.some(region => region.enabled && region.solo);
  const regions = rawRegions.map(region => ({
    ...region,
    effectiveEnabled: region.enabled && !region.muted && (!hasSolo || region.solo),
  }));
  return {
    enabledRoot,
    composerMode,
    regionCount,
    hasSolo,
    regions,
    effectiveIndices: regions.filter(region => region.effectiveEnabled).map(region => region.index),
  };
}

function collectGenerationRegionalPromptSettings() {
  const composerMode = getGenerationRegionalComposerMode();
  const regionalSnapshot = getGenerationRegionalEffectiveStateSnapshot();
  return {
    regional_prompt_enabled: String($('generation-regional-enabled')?.value || 'false') === 'true',
    regional_prompt_profile: $('generation-regional-profile')?.value || 'custom',
    regional_composer_mode: composerMode,
    regional_backend_mode: $('generation-regional-backend-mode')?.value || 'auto',
    regional_backend_capabilities: getGenerationRegionalBackendCapabilities(),
    regional_overlap_mode: $('generation-regional-overlap-mode')?.value || 'blend',
    regional_count: getGenerationRegionalCount(),
    regional_prompt_regions: generationRegionalIndices.map(index => ({
      enabled: !!regionalSnapshot.regions.find(region => region.index === index)?.effectiveEnabled,
      solo: !!$(`generation-regional-r${index}-solo`)?.checked,
      muted: !!$(`generation-regional-r${index}-mute`)?.checked,
      locked: !!$(`generation-regional-r${index}-lock`)?.checked,
      label: composerMode === 'advanced' ? trim($(`generation-regional-r${index}-label`)?.value || '') : '',
      priority: composerMode === 'advanced' ? Number($(`generation-regional-r${index}-priority`)?.value || index) : index,
      prompt: trim($(`generation-regional-r${index}-prompt`)?.value || ''),
      negative_prompt: trim($(`generation-regional-r${index}-negative-prompt`)?.value || ''),
      mask_source: composerMode === 'advanced' ? ($(`generation-regional-r${index}-mask-source`)?.value || 'rect') : 'rect',
      mask_channel: composerMode === 'advanced' ? ($(`generation-regional-r${index}-mask-channel`)?.value || 'alpha') : 'alpha',
      image_field: `regional_mask__${index}`,
      x: Number($(`generation-regional-r${index}-x`)?.value || 0) / 100,
      y: Number($(`generation-regional-r${index}-y`)?.value || 0) / 100,
      w: Number($(`generation-regional-r${index}-w`)?.value || 33) / 100,
      h: Number($(`generation-regional-r${index}-h`)?.value || 100) / 100,
      positive_strength: composerMode === 'advanced' ? Number($(`generation-regional-r${index}-positive-strength`)?.value || 1.0) : 1.0,
      negative_strength: composerMode === 'advanced' ? Number($(`generation-regional-r${index}-negative-strength`)?.value || 1.0) : 1.0,
      falloff: composerMode === 'advanced' ? Number($(`generation-regional-r${index}-falloff`)?.value || 0) : 0,
    })),
  };
}

function syncGenerationImageUpscaleUI() {
  const assist = $('generation-image-upscale-restore-assist')?.value || 'off';
  const codeformer = assist === 'codeformer';
  $('generation-image-upscale-restore-model-wrap')?.classList.toggle('is-hidden', !codeformer);
  $('generation-image-upscale-restore-fidelity-wrap')?.classList.toggle('is-hidden', !codeformer);
  $('generation-image-upscale-restore-detection-wrap')?.classList.toggle('is-hidden', !codeformer);
  const modelSelect = $('generation-image-upscale-model');
  const modelName = trim(modelSelect?.selectedOptions?.[0]?.textContent || modelSelect?.value || '');
  const realModelCount = Math.max(0, (modelSelect?.options?.length || 0) - 1);
  const scale = Number($('generation-image-upscale-scale')?.value || 2.0);
  const restoreModel = trim($('generation-image-upscale-restore-model')?.selectedOptions?.[0]?.textContent || $('generation-image-upscale-restore-model')?.value || '');
  const batchCount = $('generation-image-upscale-batch-files')?.files?.length || 0;
  const pieces = [];
  pieces.push(modelName ? `Model: ${modelName}` : (realModelCount ? 'Model: choose an upscale model' : 'Model: no upscale models found'));
  pieces.push(`${scale}× target`);
  if (codeformer) pieces.push(`CodeFormer${restoreModel ? ` · ${restoreModel}` : ''}`);
  if (batchCount) pieces.push(`${batchCount} queued in batch input`);
  if (!realModelCount) pieces.push('Install ESRGAN / UltraSharp models to enable preserve upscale models');
  if ($('generation-image-upscale-summary')) $('generation-image-upscale-summary').textContent = pieces.join(' · ');
  renderGenerationFinishFoundation();
}

function applyGenerationImageUpscaleProfile(key, { silent=false } = {}) {
  const profile = generationImageUpscaleProfiles[key];
  if (!profile) return;
  if ($('generation-image-upscale-profile')) $('generation-image-upscale-profile').value = key;
  if ($('generation-image-upscale-scale')) $('generation-image-upscale-scale').value = profile.scale;
  if ($('generation-image-upscale-resize-method')) $('generation-image-upscale-resize-method').value = profile.resize_method;
  if ($('generation-image-upscale-restore-assist')) $('generation-image-upscale-restore-assist').value = profile.restore_assist;
  if ($('generation-image-upscale-restore-fidelity')) $('generation-image-upscale-restore-fidelity').value = profile.restore_fidelity;
  syncGenerationImageUpscaleUI();
  if (!silent) setStatus('generation-status', `Image Upscale preset loaded: ${profile.label}.`, 'success');
  scheduleGenerationDraftSave();
}

function markGenerationImageUpscaleCustom() {
  if ($('generation-image-upscale-profile')) $('generation-image-upscale-profile').value = 'custom';
  syncGenerationImageUpscaleUI();
}

function collectGenerationImageUpscaleSettings() {
  return {
    image_upscale_profile: $('generation-image-upscale-profile')?.value || 'custom',
    image_upscale_model: trim($('generation-image-upscale-model')?.value || ''),
    image_upscale_scale: Number($('generation-image-upscale-scale')?.value || 2.0),
    image_upscale_resize_method: $('generation-image-upscale-resize-method')?.value || 'lanczos',
    image_upscale_restore_assist: $('generation-image-upscale-restore-assist')?.value || 'off',
    image_upscale_restore_model: trim($('generation-image-upscale-restore-model')?.value || ''),
    image_upscale_restore_fidelity: Number($('generation-image-upscale-restore-fidelity')?.value || 0.65),
    image_upscale_restore_detection: $('generation-image-upscale-restore-detection')?.value || 'retinaface_resnet50',
  };
}

function openGenerationResultsTab() {
  if (typeof window.neoGenerationSetSetupTab === 'function') {
    window.neoGenerationSetSetupTab('output');
    return;
  }
  document.querySelector('[data-generation-setup-tab="output"]')?.click();
}

async function submitGenerationImageUpscale(files, { batch=false } = {}) {
  const usable = Array.from(files || []).filter(Boolean);
  if (!usable.length) throw new Error(batch ? 'Pick one or more images for batch upscale first.' : 'Pick an image first.');
  const payload = collectGenerationImageUpscaleSettings();
  const fd = new FormData();
  fd.append('settings_json', JSON.stringify(payload));
  usable.forEach(file => fd.append('image_files', file, file.name || 'upscale.png'));
  const response = await fetch('/api/generation/image-upscale', { method:'POST', body: fd });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.detail || data.message || 'Could not queue Image Upscale.');
  const failed = Array.isArray(data.failed) ? data.failed.length : 0;
  setStatus('generation-status', `Queued Image Upscale for ${data.queued_count || usable.length} image${(data.queued_count || usable.length) === 1 ? '' : 's'}${failed ? ` (${failed} failed)` : ''}.`, failed ? 'warn' : 'success');
  openGenerationResultsTab();
  fetchGenerationState(true).catch(() => {});
  return data;
}

function resolveGenerationImageUpscaleSourceTarget() {
  if (generationPreviewActionTarget?.view_url) return generationPreviewActionTarget;
  const latestOutputs = Array.isArray(generationLatestJobSnapshot?.outputs) ? generationLatestJobSnapshot.outputs : [];
  const fallback = latestOutputs.find(item => item && item.view_url) || null;
  if (fallback) {
    setGenerationPreviewActionTarget(fallback);
    return fallback;
  }
  return null;
}

async function runGenerationSelectedImageUpscale() {
  const target = resolveGenerationImageUpscaleSourceTarget();
  if (target) {
    setStatus('generation-status', `Preparing Image Upscale from ${target.saved_filename || target.filename || 'selected result'}…`);
    const file = await fetchGenerationPreviewFile();
    const data = await submitGenerationImageUpscale([file], { batch:false });
    const queuedJob = Array.isArray(data?.jobs) ? data.jobs[0] : null;
    if (queuedJob) {
      renderGenerationJob(queuedJob);
      openGenerationResultsTab();
      if (queuedJob.id) pollGenerationJob(queuedJob.id);
    }
    return data;
  }

  const uploaded = Array.from($('generation-image-upscale-batch-files')?.files || []).filter(Boolean);
  if (uploaded.length === 1) {
    setStatus('generation-status', `No selected result found — using uploaded image ${uploaded[0]?.name || 'image'} for single-image upscale instead.`,'warn');
    const data = await submitGenerationImageUpscale([uploaded[0]], { batch:false });
    const queuedJob = Array.isArray(data?.jobs) ? data.jobs[0] : null;
    if (queuedJob) {
      renderGenerationJob(queuedJob);
      openGenerationResultsTab();
      if (queuedJob.id) pollGenerationJob(queuedJob.id);
    }
    return data;
  }

  throw new Error(uploaded.length
    ? 'No selected result found. Use Run uploaded batch for queued files, or keep just one uploaded image to use this button.'
    : 'Pick a result first, upload one image here, or wait until a generated output exists.');
}

async function runGenerationBatchImageUpscale() {
  const files = Array.from($('generation-image-upscale-batch-files')?.files || []);
  setStatus('generation-status', `Preparing Image Upscale batch for ${files.length || 0} image${files.length === 1 ? '' : 's'}…`);
  const data = await submitGenerationImageUpscale(files, { batch:true });
  const queuedJob = Array.isArray(data?.jobs) ? data.jobs[0] : null;
  if (queuedJob) {
    renderGenerationJob(queuedJob);
    openGenerationResultsTab();
    if (queuedJob.id) pollGenerationJob(queuedJob.id);
  }
  return data;
}

const generationZoomState = {
  scale: 1,
  x: 0,
  y: 0,
  dragging: false,
  startX: 0,
  startY: 0,
  baseX: 0,
  baseY: 0,
  compareMode: 'after',
  beforeUrl: '',
  afterUrl: '',
  naturalWidth: 0,
  naturalHeight: 0,
  fitScale: 1,
};
let generationLastCompareBeforeUrl = '';
let generationLastCompareAfterUrl = '';

function clampGenerationZoom(value, min=0.25, max=8) {
  return Math.min(max, Math.max(min, Number(value) || 1));
}

function getGenerationCompareBeforeUrl(active=null) {
  const item = active || getGenerationActiveOutputSnapshot?.() || generationPreviewActionTarget || generationSelectedOutputSnapshot || null;
  const direct = String(item?.before_view_url || item?.source_view_url || item?._neo_source_view_url || '').trim();
  if (direct) return direct;
  try {
    const key = generationOutputKey?.(item) || '';
    const entry = key ? generationOutputLineageState?.entries?.[key] : null;
    const parentKey = entry?.parentKey || item?.derived_from_output_id || item?.parent_output_key || '';
    const parent = parentKey ? generationOutputLineageState?.entries?.[parentKey] : null;
    const parentUrl = String(parent?.output?.view_url || '').trim();
    if (parentUrl) return parentUrl;
  } catch (_) {}
  const activeUrl = String(item?.view_url || item?.after_view_url || '').trim();
  if (generationLastCompareBeforeUrl && (!generationLastCompareAfterUrl || generationLastCompareAfterUrl === activeUrl)) return generationLastCompareBeforeUrl;
  return '';
}

function applyGenerationZoomTransform() {
  const img = $('generation-image-zoom');
  const before = $('generation-image-zoom-before');
  const scaleLabel = $('generation-zoom-scale');
  const transform = `translate(-50%, -50%) translate(${generationZoomState.x}px, ${generationZoomState.y}px) scale(${generationZoomState.scale})`;
  if (img) img.style.transform = transform;
  if (before) before.style.transform = transform;
  if (scaleLabel) scaleLabel.textContent = `${Math.round(generationZoomState.scale * 100)}%`;
}

function computeGenerationZoomFitScale() {
  const stage = $('generation-zoom-stage');
  const img = $('generation-image-zoom');
  const naturalWidth = Number(generationZoomState.naturalWidth || img?.naturalWidth || 0);
  const naturalHeight = Number(generationZoomState.naturalHeight || img?.naturalHeight || 0);
  if (!stage || !(naturalWidth > 0) || !(naturalHeight > 0)) return 1;
  const pad = 36;
  const fitW = Math.max(1, stage.clientWidth - pad) / naturalWidth;
  const fitH = Math.max(1, stage.clientHeight - pad) / naturalHeight;
  return clampGenerationZoom(Math.min(1, fitW, fitH));
}

function prepareGenerationZoomNaturalSize() {
  const img = $('generation-image-zoom');
  const before = $('generation-image-zoom-before');
  const naturalWidth = Number(img?.naturalWidth || generationZoomState.naturalWidth || 0);
  const naturalHeight = Number(img?.naturalHeight || generationZoomState.naturalHeight || 0);
  if (!(naturalWidth > 0) || !(naturalHeight > 0)) return;
  generationZoomState.naturalWidth = naturalWidth;
  generationZoomState.naturalHeight = naturalHeight;
  [img, before].forEach(node => {
    if (!node) return;
    node.style.width = `${naturalWidth}px`;
    node.style.height = `${naturalHeight}px`;
  });
  generationZoomState.fitScale = computeGenerationZoomFitScale();
}

function resetGenerationZoomView(scale='fit') {
  prepareGenerationZoomNaturalSize();
  const nextScale = scale === 'fit' ? (generationZoomState.fitScale || computeGenerationZoomFitScale() || 1) : scale;
  generationZoomState.scale = clampGenerationZoom(nextScale);
  generationZoomState.x = 0;
  generationZoomState.y = 0;
  applyGenerationZoomTransform();
}

function setGenerationCompareMode(mode='after') {
  const stage = $('generation-zoom-stage');
  const before = $('generation-image-zoom-before');
  const label = $('generation-compare-label');
  const range = $('generation-compare-range');
  const wipe = $('generation-compare-wipe');
  const hasBefore = !!generationZoomState.beforeUrl;
  generationZoomState.compareMode = hasBefore ? mode : 'after';
  const isBefore = generationZoomState.compareMode === 'before';
  const isSlider = generationZoomState.compareMode === 'slider';
  stage?.classList.toggle('is-before', isBefore);
  stage?.classList.toggle('is-slider', isSlider);
  before?.classList.toggle('hidden', !hasBefore || generationZoomState.compareMode === 'after');
  range?.classList.toggle('hidden', !hasBefore || !isSlider);
  wipe?.classList.toggle('hidden', !hasBefore || !isSlider);
  label?.classList.toggle('hidden', !hasBefore);
  if (label) label.textContent = isSlider ? 'Slider compare' : (isBefore ? 'Before' : 'After');
  updateGenerationCompareSlider();
}

function updateGenerationCompareSlider() {
  const before = $('generation-image-zoom-before');
  const range = $('generation-compare-range');
  const wipe = $('generation-compare-wipe');
  const pct = Math.min(100, Math.max(0, Number(range?.value || 50)));
  if (before && generationZoomState.compareMode === 'slider') before.style.clipPath = `inset(0 ${100 - pct}% 0 0)`;
  if (wipe) wipe.style.left = `${pct}%`;
}

function bindGenerationZoomModalControls() {
  const stage = $('generation-zoom-stage');
  const range = $('generation-compare-range');
  if (!stage || stage.dataset.zoomBound === '1') return;
  stage.dataset.zoomBound = '1';
  stage.addEventListener('wheel', event => {
    event.preventDefault();
    const prev = generationZoomState.scale;
    const factor = event.deltaY < 0 ? 1.12 : 0.89;
    const next = clampGenerationZoom(prev * factor);
    const rect = stage.getBoundingClientRect();
    const cx = event.clientX - rect.left - rect.width / 2;
    const cy = event.clientY - rect.top - rect.height / 2;
    if (prev > 0 && next !== prev) {
      generationZoomState.x = cx - (cx - generationZoomState.x) * (next / prev);
      generationZoomState.y = cy - (cy - generationZoomState.y) * (next / prev);
    }
    generationZoomState.scale = next;
    applyGenerationZoomTransform();
  }, { passive:false });
  stage.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    generationZoomState.dragging = true;
    generationZoomState.startX = event.clientX;
    generationZoomState.startY = event.clientY;
    generationZoomState.baseX = generationZoomState.x;
    generationZoomState.baseY = generationZoomState.y;
    stage.classList.add('is-dragging');
    try { stage.setPointerCapture(event.pointerId); } catch (_) {}
  });
  stage.addEventListener('pointermove', event => {
    if (!generationZoomState.dragging) return;
    generationZoomState.x = generationZoomState.baseX + (event.clientX - generationZoomState.startX);
    generationZoomState.y = generationZoomState.baseY + (event.clientY - generationZoomState.startY);
    applyGenerationZoomTransform();
  });
  const endDrag = event => {
    generationZoomState.dragging = false;
    stage.classList.remove('is-dragging');
    try { stage.releasePointerCapture(event.pointerId); } catch (_) {}
  };
  stage.addEventListener('pointerup', endDrag);
  stage.addEventListener('pointercancel', endDrag);
  stage.addEventListener('dblclick', () => resetGenerationZoomView('fit'));
  $('btn-generation-zoom-reset')?.addEventListener('click', () => resetGenerationZoomView('fit'));
  $('btn-generation-zoom-actual')?.addEventListener('click', () => resetGenerationZoomView(1));
  $('btn-generation-compare-toggle')?.addEventListener('click', () => setGenerationCompareMode(generationZoomState.compareMode === 'before' ? 'after' : 'before'));
  $('btn-generation-compare-slider')?.addEventListener('click', () => setGenerationCompareMode(generationZoomState.compareMode === 'slider' ? 'after' : 'slider'));
  range?.addEventListener('input', updateGenerationCompareSlider);
}

function hydrateGenerationZoomModal(source='', options={}) {
  const modal = $('generation-image-zoom-modal');
  const img = $('generation-image-zoom');
  const before = $('generation-image-zoom-before');
  const afterUrl = String(source || '').trim();
  if (!modal || !img || !afterUrl) return false;
  const active = options.activeOutput || getGenerationActiveOutputSnapshot?.() || generationPreviewActionTarget || generationSelectedOutputSnapshot || null;
  const beforeUrl = String(options.beforeUrl || getGenerationCompareBeforeUrl(active) || '').trim();
  generationZoomState.afterUrl = afterUrl;
  generationZoomState.beforeUrl = beforeUrl && beforeUrl !== afterUrl ? beforeUrl : '';
  generationZoomState.naturalWidth = 0;
  generationZoomState.naturalHeight = 0;
  img.onload = () => resetGenerationZoomView('fit');
  img.src = afterUrl;
  if (before) {
    if (generationZoomState.beforeUrl) before.src = generationZoomState.beforeUrl;
    else before.removeAttribute('src');
  }
  ['btn-generation-compare-toggle','btn-generation-compare-slider'].forEach(id => $(id)?.classList.toggle('hidden', !generationZoomState.beforeUrl));
  bindGenerationZoomModalControls();
  resetGenerationZoomView('fit');
  setGenerationCompareMode('after');
  modal.classList.remove('hidden');
  document.body.classList.add('modal-open');
  return true;
}

function openGenerationZoomModal() {
  const source = $('generation-live-preview')?.getAttribute('src') || generationPreviewActionTarget?.view_url || '';
  hydrateGenerationZoomModal(source);
}

function closeGenerationZoomModal() {
  const modal = $('generation-image-zoom-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  generationZoomState.dragging = false;
  setGenerationCompareMode('after');
  if ($('backend-manager-modal')?.classList.contains('hidden') !== false) document.body.classList.remove('modal-open');
}

function collectGenerationDraft() {
  return window.NeoGenerationDraftState.collectGenerationDraft.apply(this, arguments);
}

function makeGenerationShellSnapshotId() {
  return `shell_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function cloneGenerationShellSnapshotDraft(draft) {
  try {
    return JSON.parse(JSON.stringify(draft || {}));
  } catch (_) {
    return draft && typeof draft === 'object' ? { ...draft } : {};
  }
}

function normalizeGenerationShellSnapshotEntry(item, { forceNewId=false } = {}) {
  if (!item || typeof item !== 'object') return null;
  const draft = item.draft && typeof item.draft === 'object'
    ? cloneGenerationShellSnapshotDraft(item.draft)
    : null;
  if (!draft) return null;
  const id = forceNewId ? makeGenerationShellSnapshotId() : String(item.id || makeGenerationShellSnapshotId());
  const name = String(item.name || 'Untitled preset').trim() || 'Untitled preset';
  const updatedAt = Number(item.updated_at || draft?.updated_at || Date.now()) || Date.now();
  return {
    id,
    name,
    updated_at: updatedAt,
    draft,
  };
}

function loadGenerationShellSnapshots() {
  try {
    const raw = localStorage.getItem(generationSnapshotStorageKey);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(item => normalizeGenerationShellSnapshotEntry(item))
      .filter(Boolean);
  } catch (_) {
    return [];
  }
}

function saveGenerationShellSnapshots(list) {
  try {
    const safeList = Array.isArray(list)
      ? list.map(item => normalizeGenerationShellSnapshotEntry(item)).filter(Boolean)
      : [];
    localStorage.setItem(generationSnapshotStorageKey, JSON.stringify(safeList));
  } catch (_) {}
}

function getGenerationDefaultShellSnapshotId() {
  try {
    return String(localStorage.getItem(generationDefaultSnapshotStorageKey) || '').trim();
  } catch (_) {
    return '';
  }
}

function setGenerationDefaultShellSnapshotId(id) {
  const value = String(id || '').trim();
  try {
    if (!value) localStorage.removeItem(generationDefaultSnapshotStorageKey);
    else localStorage.setItem(generationDefaultSnapshotStorageKey, value);
  } catch (_) {}
}

function clearGenerationDefaultShellSnapshotId() {
  setGenerationDefaultShellSnapshotId('');
}


const BUILTIN_GENERATION_SHELL_PRESETS = [
  { id:'builtin:create_portrait_safe', name:'Starter · Fresh portrait', recipeId:'create_portrait_safe' },
  { id:'builtin:create_square_safe', name:'Starter · Square social', recipeId:'create_square_safe' },
  { id:'builtin:create_landscape_safe', name:'Starter · Landscape frame', recipeId:'create_landscape_safe' },
  { id:'builtin:reference_same_face', name:'Starter · IP-Adapter match', recipeId:'reference_same_face' },
  { id:'builtin:repair_small_area', name:'Starter · Repair area', recipeId:'repair_small_area' },
  { id:'builtin:cleanup_remove_object', name:'Starter · Remove object', recipeId:'cleanup_remove_object' },
  { id:'builtin:finish_preserve_2x', name:'Starter · Finish preserve 2×', recipeId:'finish_preserve_2x' },
  { id:'builtin:recover_output_rebuild', name:'Starter · Recover from output', recipeId:'recover_output_rebuild' },
];

function listBuiltinGenerationShellPresets() {
  return BUILTIN_GENERATION_SHELL_PRESETS.slice();
}

function isBuiltinGenerationShellPresetId(id='') {
  return String(id || '').trim().startsWith('builtin:');
}

function findBuiltinGenerationShellPreset(id='') {
  const target = String(id || '').trim();
  return listBuiltinGenerationShellPresets().find(item => String(item?.id || '') === target) || null;
}

function emitGenerationPresetChanged(presetId='') {
  try {
    document.dispatchEvent(new CustomEvent('neo-generation-preset-changed', { detail: { presetId: String(presetId || '') } }));
  } catch (_) {}
}

function syncGenerationShellSnapshotActions() {
  const selectedId = String($('generation-shell-snapshot-select')?.value || '').trim();
  const defaultId = getGenerationDefaultShellSnapshotId();
  const hasSelection = !!selectedId;
  const hasDefault = !!defaultId;
  const isBuiltin = isBuiltinGenerationShellPresetId(selectedId);
  const isSelectedDefault = !!selectedId && selectedId === defaultId;
  ['btn-generation-load-snapshot'].forEach(id => {
    const btn = $(id);
    if (!btn) return;
    btn.disabled = !hasSelection;
    btn.setAttribute('aria-disabled', hasSelection ? 'false' : 'true');
    btn.title = hasSelection ? (btn.getAttribute('data-default-title') || btn.title || '') : 'Pick a workspace preset first';
  });
  ['btn-generation-update-snapshot', 'btn-generation-rename-snapshot', 'btn-generation-duplicate-snapshot', 'btn-generation-export-snapshot', 'btn-generation-delete-snapshot'].forEach(id => {
    const btn = $(id);
    if (!btn) return;
    const enabled = hasSelection && !isBuiltin;
    btn.disabled = !enabled;
    btn.setAttribute('aria-disabled', enabled ? 'false' : 'true');
    btn.title = !hasSelection ? 'Pick a workspace preset first' : (isBuiltin ? 'Built-in starter presets are load-only. Save your own workspace preset if you want to edit or export one.' : (btn.getAttribute('data-default-title') || btn.title || ''));
  });
  const defaultBtn = $('btn-generation-set-default-snapshot');
  if (defaultBtn) {
    const canSetDefault = hasSelection && !isSelectedDefault;
    defaultBtn.disabled = !canSetDefault;
    defaultBtn.setAttribute('aria-disabled', canSetDefault ? 'false' : 'true');
    defaultBtn.title = !hasSelection
      ? 'Pick a workspace preset first'
      : (isSelectedDefault ? 'Selected workspace preset is already the default startup preset' : 'Make the selected workspace preset load automatically on startup');
  }
  const clearBtn = $('btn-generation-clear-default-snapshot');
  if (clearBtn) {
    clearBtn.disabled = !hasDefault;
    clearBtn.setAttribute('aria-disabled', hasDefault ? 'false' : 'true');
    clearBtn.title = hasDefault ? 'Stop auto-loading the default workspace preset on startup' : 'No default workspace preset is set yet';
  }
}

function renderGenerationShellSnapshotSelect(selectedId='') {
  const select = $('generation-shell-snapshot-select');
  if (!select) return;
  const snapshots = loadGenerationShellSnapshots().sort((a, b) => Number(b?.updated_at || 0) - Number(a?.updated_at || 0));
  const builtins = listBuiltinGenerationShellPresets();
  const defaultId = getGenerationDefaultShellSnapshotId();
  const current = String(selectedId || select.value || '');
  select.innerHTML = '<option value="">Workspace presets…</option>';
  if (builtins.length) {
    const group = document.createElement('optgroup');
    group.label = 'Built-in starters';
    builtins.forEach(item => {
      const opt = document.createElement('option');
      opt.value = String(item.id || '');
      const prefix = defaultId && defaultId === opt.value ? '★ ' : '';
      opt.textContent = `${prefix}${String(item.name || 'Built-in starter')}`;
      if (current && current === opt.value) opt.selected = true;
      group.appendChild(opt);
    });
    select.appendChild(group);
  }
  if (snapshots.length) {
    const group = document.createElement('optgroup');
    group.label = 'Saved workspace presets';
    snapshots.forEach(item => {
      const opt = document.createElement('option');
      opt.value = String(item.id || '');
      const prefix = defaultId && defaultId === opt.value ? '★ ' : '';
      opt.textContent = `${prefix}${String(item.name || 'Untitled preset')}`;
      if (current && current === opt.value) opt.selected = true;
      group.appendChild(opt);
    });
    select.appendChild(group);
  }
  syncGenerationShellSnapshotActions();
  emitGenerationPresetChanged(select.value || current || '');
}

function findGenerationShellSnapshotById(id) {
  const target = String(id || '');
  if (!target) return null;
  if (isBuiltinGenerationShellPresetId(target)) return findBuiltinGenerationShellPreset(target);
  return loadGenerationShellSnapshots().find(item => String(item?.id || '') === target) || null;
}

function applyBuiltinGenerationShellPreset({ item, silent=false, statusText='' } = {}) {
  if (!item?.recipeId || typeof window.neoGenerationApplyRecipe !== 'function') return false;
  window.neoGenerationApplyRecipe(item.recipeId);
  renderGenerationShellSnapshotSelect(String(item.id || ''));
  syncGenerationShellSnapshotActions();
  emitGenerationPresetChanged(String(item.id || ''));
  if (!silent) setStatus('generation-status', statusText || `Loaded starter preset: ${item.name || 'Built-in starter'}`, 'success');
  return true;
}

function applyGenerationShellSnapshotItem(item, { silent=false, statusText='' } = {}) {
  if (!item?.draft) return false;
  generationActiveStyles = [];
  pendingGenerationDraft = item.draft;
  applyGenerationDraft(item.draft);
  renderGenerationShellSnapshotSelect(String(item.id || ''));
  syncGenerationShellSnapshotActions();
  refreshGenerationSectionStateBadges();
  scheduleGenerationSectionBadgeRefresh();
  emitGenerationPresetChanged(String(item.id || ''));
  if (!silent) setStatus('generation-status', statusText || `Loaded workspace preset: ${item.name || 'Untitled preset'}`, 'success');
  return true;
}

function autoLoadDefaultGenerationShellSnapshot({ silent=true } = {}) {
  const defaultId = getGenerationDefaultShellSnapshotId();
  if (!defaultId) return false;
  const item = findGenerationShellSnapshotById(defaultId);
  if (item?.recipeId) {
    try {
      applyBuiltinGenerationShellPreset({ item, silent:true });
      if (!silent) setStatus('generation-status', `Loaded default workspace preset: ${item.name || 'Built-in starter'}`, 'success');
      return true;
    } catch (e) {
      clearGenerationDefaultShellSnapshotId();
      renderGenerationShellSnapshotSelect('');
      syncGenerationShellSnapshotActions();
      setStatus('generation-status', e?.message || 'Default built-in preset could not be applied, so Neo fell back to a clean workspace.', 'warn');
      return false;
    }
  }
  if (!item?.draft) {
    clearGenerationDefaultShellSnapshotId();
    renderGenerationShellSnapshotSelect('');
    syncGenerationShellSnapshotActions();
    if (!silent) setStatus('generation-status', 'Default workspace preset was missing, so Neo fell back to a clean workspace.', 'warn');
    return false;
  }
  try {
    applyGenerationShellSnapshotItem(item, { silent:true });
    if (!silent) setStatus('generation-status', `Loaded default workspace preset: ${item.name || 'Untitled preset'}`, 'success');
    return true;
  } catch (e) {
    clearGenerationDefaultShellSnapshotId();
    renderGenerationShellSnapshotSelect('');
    syncGenerationShellSnapshotActions();
    setStatus('generation-status', e?.message || 'Default workspace preset could not be applied, so Neo fell back to a clean workspace.', 'warn');
    return false;
  }
}

function setSelectedGenerationShellSnapshotAsDefault() {
  const selectedId = String($('generation-shell-snapshot-select')?.value || '').trim();
  const item = findGenerationShellSnapshotById(selectedId);
  if (!item) {
    setStatus('generation-status', 'Pick a workspace preset first.', 'warn');
    return;
  }
  setGenerationDefaultShellSnapshotId(selectedId);
  renderGenerationShellSnapshotSelect(selectedId);
  syncGenerationShellSnapshotActions();
  setStatus('generation-status', `Default workspace preset set: ${item.name || 'Untitled preset'}`, 'success');
}

function clearDefaultGenerationShellSnapshot() {
  const defaultId = getGenerationDefaultShellSnapshotId();
  if (!defaultId) {
    setStatus('generation-status', 'No default workspace preset is set yet.', 'warn');
    return;
  }
  clearGenerationDefaultShellSnapshotId();
  renderGenerationShellSnapshotSelect($('generation-shell-snapshot-select')?.value || '');
  syncGenerationShellSnapshotActions();
  emitGenerationPresetChanged($('generation-shell-snapshot-select')?.value || '');
  setStatus('generation-status', 'Default workspace preset cleared.', 'success');
}

function sanitizeGenerationShellSnapshotFilename(name='') {
  return String(name || 'generation-workspace-preset')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'generation-workspace-preset';
}

function renameSelectedGenerationShellSnapshot() {
  const selectedId = String($('generation-shell-snapshot-select')?.value || '').trim();
  const snapshots = loadGenerationShellSnapshots();
  const item = snapshots.find(entry => String(entry?.id || '') === selectedId);
  if (!item) {
    setStatus('generation-status', 'Pick a workspace preset first.', 'warn');
    return;
  }
  const nextName = String(window.prompt('Rename this workspace preset:', item.name || 'Untitled preset') || '').trim();
  if (!nextName) {
    setStatus('generation-status', 'Preset rename cancelled.', 'warn');
    return;
  }
  item.name = nextName;
  item.updated_at = Date.now();
  saveGenerationShellSnapshots(snapshots);
  renderGenerationShellSnapshotSelect(selectedId);
  syncGenerationShellSnapshotActions();
  setStatus('generation-status', `Renamed workspace preset to: ${nextName}`, 'success');
}

function duplicateSelectedGenerationShellSnapshot() {
  const selectedId = String($('generation-shell-snapshot-select')?.value || '').trim();
  const snapshots = loadGenerationShellSnapshots();
  const item = snapshots.find(entry => String(entry?.id || '') === selectedId);
  if (isBuiltinGenerationShellPresetId(selectedId)) {
    setStatus('generation-status', 'Built-in starter presets are load-only. Load one, then save your own preset if you want a custom copy.', 'warn');
    return;
  }
  if (!item?.draft) {
    setStatus('generation-status', 'Pick a workspace preset first.', 'warn');
    return;
  }
  const suggestedName = `${item.name || 'Untitled preset'} copy`;
  const nextName = String(window.prompt('Name the duplicated workspace preset:', suggestedName) || '').trim();
  if (!nextName) {
    setStatus('generation-status', 'Preset duplicate cancelled.', 'warn');
    return;
  }
  const duplicate = normalizeGenerationShellSnapshotEntry({
    name: nextName,
    updated_at: Date.now(),
    draft: cloneGenerationShellSnapshotDraft(item.draft),
  }, { forceNewId:true });
  if (!duplicate) {
    setStatus('generation-status', 'Neo could not duplicate that workspace preset.', 'error');
    return;
  }
  snapshots.push(duplicate);
  saveGenerationShellSnapshots(snapshots);
  renderGenerationShellSnapshotSelect(duplicate.id);
  syncGenerationShellSnapshotActions();
  setStatus('generation-status', `Duplicated workspace preset: ${nextName}`, 'success');
}

function exportSelectedGenerationShellSnapshot() {
  const selectedId = String($('generation-shell-snapshot-select')?.value || '').trim();
  const item = findGenerationShellSnapshotById(selectedId);
  if (isBuiltinGenerationShellPresetId(selectedId)) {
    setStatus('generation-status', 'Built-in starter presets are load-only. Save your own preset if you want an exportable copy.', 'warn');
    return;
  }
  if (!item?.draft) {
    setStatus('generation-status', 'Pick a workspace preset first.', 'warn');
    return;
  }
  const payload = {
    kind: 'neo_generation_shell_preset',
    exported_at: new Date().toISOString(),
    preset: {
      id: String(item.id || ''),
      name: String(item.name || 'Untitled preset'),
      updated_at: Number(item.updated_at || Date.now()),
      draft: cloneGenerationShellSnapshotDraft(item.draft),
    },
  };
  try {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = href;
    link.download = `${sanitizeGenerationShellSnapshotFilename(item.name)}.json`;
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
      link.remove();
      URL.revokeObjectURL(href);
    }, 0);
    setStatus('generation-status', `Exported workspace preset: ${item.name || 'Untitled preset'}`, 'success');
  } catch (e) {
    setStatus('generation-status', e?.message || 'Neo could not export that workspace preset.', 'error');
  }
}

function triggerGenerationShellSnapshotImport() {
  const input = $('generation-shell-snapshot-import-file');
  if (!input) {
    setStatus('generation-status', 'Preset import input is missing.', 'error');
    return;
  }
  input.value = '';
  input.click();
}

function parseGenerationShellSnapshotImportPayload(rawText='') {
  const parsed = JSON.parse(String(rawText || 'null'));
  let items = [];
  if (parsed?.kind === 'neo_generation_shell_preset' && parsed.preset) {
    items = [parsed.preset];
  } else if (parsed?.kind === 'neo_generation_shell_preset_pack' && Array.isArray(parsed.presets)) {
    items = parsed.presets;
  } else if (Array.isArray(parsed?.presets)) {
    items = parsed.presets;
  } else if (Array.isArray(parsed)) {
    items = parsed;
  } else if (parsed?.draft && typeof parsed.draft === 'object') {
    items = [parsed];
  }
  return items
    .map((item, index) => normalizeGenerationShellSnapshotEntry({
      name: String(item?.name || item?.preset?.name || '').trim() || `Imported preset ${index + 1}`,
      updated_at: Date.now(),
      draft: item?.draft && typeof item.draft === 'object'
        ? item.draft
        : (item?.preset?.draft && typeof item.preset.draft === 'object' ? item.preset.draft : null),
    }, { forceNewId:true }))
    .filter(Boolean);
}

async function handleGenerationShellSnapshotImportSelection(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  try {
    const rawText = await file.text();
    const imported = parseGenerationShellSnapshotImportPayload(rawText);
    if (!imported.length) {
      setStatus('generation-status', 'That file did not contain any valid workspace presets.', 'warn');
      return;
    }
    const snapshots = loadGenerationShellSnapshots();
    snapshots.push(...imported);
    saveGenerationShellSnapshots(snapshots);
    const lastId = imported[imported.length - 1]?.id || '';
    renderGenerationShellSnapshotSelect(lastId);
    syncGenerationShellSnapshotActions();
    setStatus('generation-status', imported.length === 1 ? `Imported workspace preset: ${imported[0]?.name || 'Untitled preset'}` : `Imported ${imported.length} workspace presets.`, 'success');
  } catch (e) {
    setStatus('generation-status', e?.message || 'Neo could not import that preset file.', 'error');
  } finally {
    if (event?.target) event.target.value = '';
  }
}

function generationAccordionBadgeClass(tone='enabled') {
  if (window.NeoGenerationAccordionSystem?.badgeClassFromTone) return window.NeoGenerationAccordionSystem.badgeClassFromTone(tone);
  if (['enabled', 'ready', 'on'].includes(String(tone || '').toLowerCase())) return 'is-enabled';
  if (['detail', 'meta', 'count'].includes(String(tone || '').toLowerCase())) return 'is-detail';
  return 'is-disabled';
}

function ensureGenerationAccordionHeaderBadges(accordionId, primaryId, detailId) {
  if (window.NeoGenerationAccordionSystem?.ensureHeaderBadges) return window.NeoGenerationAccordionSystem.ensureHeaderBadges(accordionId, primaryId, detailId);
  return { primary:null, detail:null };
}

function setGenerationAccordionHeaderBadges({ accordionId, primaryId, detailId, primaryText, primaryTone='enabled', detailText='', detailTone='detail' }) {
  if (window.NeoGenerationAccordionSystem?.setHeaderState) {
    return window.NeoGenerationAccordionSystem.setHeaderState(accordionId, { accordionId, primaryId, detailId, primaryText, primaryTone, detailText, detailTone, active: ['enabled', 'ready', 'on'].includes(String(primaryTone || '').toLowerCase()) });
  }
}

function getGenerationSelectedOptionLabel(id) {
  const el = $(id);
  const label = el?.selectedOptions?.[0]?.textContent || '';
  return String(label || '').trim();
}

function countGenerationEnabledLoras() {
  let count = 0;
  document.querySelectorAll('#generation-lora-extra-list .generation-lora-row').forEach(row => {
    const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
    const name = trim(row.querySelector('.generation-lora-name')?.value || '');
    if (enabled && name) count += 1;
  });
  return count;
}

function countGenerationSelectedTiTokens() {
  const positive = $('generation-positive')?.value || '';
  const negative = $('generation-negative')?.value || '';
  const tokens = new Set();
  const entries = Array.isArray(generationTiLibraryState.entries) ? generationTiLibraryState.entries : [];
  entries.forEach(rec => {
    const token = generationTiPromptTokenFromRecord(rec);
    if (token && (promptContainsGenerationToken(positive, token) || promptContainsGenerationToken(negative, token))) tokens.add(token.toLowerCase());
  });
  const currentToken = trim($('generation-ti-library-token')?.value || generationTiPromptTokenFromRecord(generationTiLibraryState.currentRecord || {}));
  if (currentToken && (promptContainsGenerationToken(positive, currentToken) || promptContainsGenerationToken(negative, currentToken))) tokens.add(currentToken.toLowerCase());
  return tokens.size;
}

function countGenerationEnabledDetailers() {
  let count = !!$('generation-detailer-enabled')?.checked ? 1 : 0;
  document.querySelectorAll('#generation-detailer-extra-list .generation-detailer-row').forEach(row => {
    if (isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'))) count += 1;
  });
  return count;
}

function countGenerationEnabledControlnets() {
  let count = 0;
  if (isGenerationUnitEnabledFromCheckbox($('generation-controlnet-enabled')) && trim($('generation-controlnet-name')?.value || '')) count += 1;
  document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row').forEach(row => {
    const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
    const model = trim(row.querySelector('.generation-controlnet-name')?.value || '');
    if (enabled && model) count += 1;
  });
  return count;
}

function countGenerationEnabledIpAdapters() {
  let count = 0;
  const primaryMode = trim($('generation-ipadapter-mode')?.value || 'standard') || 'standard';
  const primaryModel = trim($('generation-ipadapter-name')?.value || '');
  const primaryClip = trim($('generation-ipadapter-clip-vision')?.value || '');
  if (isGenerationUnitEnabledFromCheckbox($('generation-ipadapter-enabled')) && primaryClip && (primaryMode === 'faceid' || primaryModel)) count += 1;
  document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row').forEach(row => {
    const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
    const mode = trim(row.querySelector('.generation-ipadapter-mode')?.value || 'standard') || 'standard';
    const model = trim(row.querySelector('.generation-ipadapter-name')?.value || '');
    const clip = trim(row.querySelector('.generation-ipadapter-clip-vision')?.value || '');
    if (enabled && clip && (mode === 'faceid' || model)) count += 1;
  });
  return count;
}

function buildGenerationSectionStatusPayload(specOrId) {
  return window.NeoGenerationDraftState.buildGenerationSectionStatusPayload.apply(this, arguments);
}

function refreshGenerationSectionStateBadges() {
  const system = window.NeoGenerationAccordionSystem;
  const sections = typeof window.listNeoGenerationSections === 'function'
    ? window.listNeoGenerationSections()
    : [];
  sections.forEach(spec => {
    if (!spec?.status_pattern) return;
    const payload = buildGenerationSectionStatusPayload(spec);
    if (!payload) return;
    if (system?.setHeaderState) {
      system.setHeaderState(spec, payload);
      return;
    }
    setGenerationAccordionHeaderBadges({
      accordionId: spec.id,
      primaryText: payload.primaryText || (payload.active ? 'Enabled' : 'Disabled'),
      primaryTone: payload.active ? 'enabled' : 'disabled',
      detailText: payload.detailText || '',
      detailTone: payload.detailTone || 'detail',
    });
  });
}

function scheduleGenerationSectionBadgeRefresh(delays=[0, 120, 420, 900]) {
  const queue = Array.isArray(delays) && delays.length ? delays : [0];
  queue.forEach(delay => {
    window.setTimeout(() => {
      try {
        refreshGenerationSectionStateBadges();
      } catch (_) {}
    }, Number(delay || 0));
  });
}


function saveCurrentGenerationShellSnapshot({ updateSelected=false } = {}) {
  const snapshots = loadGenerationShellSnapshots();
  const selectedId = String($('generation-shell-snapshot-select')?.value || '');
  const selected = updateSelected ? (snapshots.find(item => String(item?.id || '') === selectedId) || null) : null;
  if (updateSelected && !selected) {
    setStatus('generation-status', 'Pick a workspace preset first if you want to update one.', 'warn');
    return;
  }
  const suggestedName = selected?.name || '';
  const name = String(window.prompt(updateSelected ? 'Update this workspace preset name if needed:' : 'Name this workspace preset:', suggestedName) || '').trim();
  if (!name) {
    setStatus('generation-status', 'Workspace preset save cancelled.', 'warn');
    return;
  }
  const draft = collectGenerationDraft();
  const now = Date.now();
  if (selected) {
    selected.name = name;
    selected.updated_at = now;
    selected.draft = draft;
  } else {
    snapshots.push({ id: makeGenerationShellSnapshotId(), name, updated_at: now, draft });
  }
  saveGenerationShellSnapshots(snapshots);
  const nextId = selected?.id || snapshots[snapshots.length - 1]?.id || '';
  renderGenerationShellSnapshotSelect(nextId);
  syncGenerationShellSnapshotActions();
  emitGenerationPresetChanged(nextId);
  setStatus('generation-status', selected ? `Updated workspace preset: ${name}` : `Saved workspace preset: ${name}`, 'success');
}

function loadSelectedGenerationShellSnapshot() {
  const selectedId = String($('generation-shell-snapshot-select')?.value || '');
  const item = findGenerationShellSnapshotById(selectedId);
  if (!item) {
    setStatus('generation-status', 'Pick a workspace preset first.', 'warn');
    return;
  }
  if (item.recipeId) {
    applyBuiltinGenerationShellPreset({ item, silent:false, statusText: `Loaded starter preset: ${item.name || 'Built-in starter'}` });
    return;
  }
  if (!item?.draft) {
    setStatus('generation-status', 'Pick a workspace preset first.', 'warn');
    return;
  }
  applyGenerationShellSnapshotItem(item, { silent:false, statusText: `Loaded workspace preset: ${item.name || 'Untitled preset'}` });
}

function deleteSelectedGenerationShellSnapshot() {
  const selectedId = String($('generation-shell-snapshot-select')?.value || '');
  const item = findGenerationShellSnapshotById(selectedId);
  if (!item) {
    setStatus('generation-status', 'Pick a workspace preset first.', 'warn');
    return;
  }
  if (item.recipeId) {
    setStatus('generation-status', 'Built-in starter presets cannot be deleted.', 'warn');
    return;
  }
  const ok = window.confirm(`Delete workspace preset "${item.name || 'Untitled preset'}"?`);
  if (!ok) return;
  const next = loadGenerationShellSnapshots().filter(entry => String(entry?.id || '') !== selectedId);
  saveGenerationShellSnapshots(next);
  if (getGenerationDefaultShellSnapshotId() === selectedId) clearGenerationDefaultShellSnapshotId();
  renderGenerationShellSnapshotSelect('');
  syncGenerationShellSnapshotActions();
  setStatus('generation-status', `Deleted workspace preset: ${item.name || 'Untitled preset'}`, 'success');
}

function scheduleGenerationDraftSave() {
  if (generationDraftSaveTimer) window.clearTimeout(generationDraftSaveTimer);
  generationDraftSaveTimer = window.setTimeout(() => {
    generationDraftSaveTimer = null;
    refreshGenerationSectionStateBadges();
  }, 40);
}

function applyGenerationDraft(draft) {
  return window.NeoGenerationDraftState.applyGenerationDraft.apply(this, arguments);
}

function buildGenerationResetDraft({ preserveOutput=true } = {}) {
  return window.NeoGenerationDraftState.buildGenerationResetDraft.apply(this, arguments);
}

async function resetGenerationShell({ preserveOutput=true } = {}) {
  const ok = window.confirm('Reset the current generation workspace back to defaults?');
  if (!ok) return;
  const draft = buildGenerationResetDraft({ preserveOutput });
  generationActiveStyles = [];
  pendingGenerationDraft = null;
  applyGenerationDraft(draft);
  if ($('generation-style-select')) $('generation-style-select').value = '';
  if ($('generation-source-image')) $('generation-source-image').value = '';
  if ($('generation-mask-image')) $('generation-mask-image').value = '';
  if ($('generation-control-image')) $('generation-control-image').value = '';
  if ($('generation-ipadapter-image')) $('generation-ipadapter-image').value = '';
  document.querySelectorAll('.generation-control-image, .generation-ipadapter-image').forEach(input => { try { input.value = ''; } catch (_) {} });
  renderGenerationActiveStyles();
  generationSourceImageInfo = { width:0, height:0, name:'', size:0 };
  renderGenerationOutpaintSummary();
  syncGenerationCleanupUI();
  syncGenerationIdentityUI();
  refreshGenerationSectionStateBadges();
  setStatus('generation-status', 'Generation workspace reset to defaults.', 'success');
}

function generationOutputKey(item) {
  if (!item || typeof item !== 'object') return '';
  return String(item.saved_path || item.saved_filename || item.filename || '');
}

function cloneGenerationOutputSnapshot(item) {
  if (!item || typeof item !== 'object') return null;
  const source = { ...item };
  const saveLane = source.save_lane || source.save_mode_override || source.output_mode || source.mode || '';
  const record = {
    ...source,
    output_id: source.output_id || generationOutputKey(source) || source.id || '',
    output_key: generationOutputKey(source),
    job_id: source.job_id || source.jobId || '',
    source_kind: source.imported ? 'imported' : (source.source_kind || source.source || 'generated'),
    save_lane: String(saveLane || '').trim().toLowerCase() || inferGenerationPreviewSaveMode(source),
    workflow_origin: source.workflow_origin || source.workflow_type || source.mode || '',
    derived_from_output_id: source.derived_from_output_id || source.parent_output_id || source.parentKey || '',
    derived_from_job_id: source.derived_from_job_id || '',
    stage: source.stage || '',
    locked_at: Date.now(),
    is_preview_source_locked: true,
  };
  return record;
}

function setGenerationActiveOutputSnapshot(item, { syncPreviewTarget=true } = {}) {
  const next = cloneGenerationOutputSnapshot(item);
  generationActiveOutputSnapshot = next ? { ...next } : null;
  generationSelectedOutputSnapshot = generationActiveOutputSnapshot ? { ...generationActiveOutputSnapshot } : null;
  if (syncPreviewTarget) generationPreviewActionTarget = generationActiveOutputSnapshot && generationActiveOutputSnapshot.view_url ? { ...generationActiveOutputSnapshot } : null;
  updateGenerationPreviewActionState?.();
  return generationActiveOutputSnapshot ? { ...generationActiveOutputSnapshot } : null;
}

function clearGenerationActiveOutputSnapshot({ syncPreviewTarget=true } = {}) {
  generationActiveOutputSnapshot = null;
  generationSelectedOutputSnapshot = null;
  if (syncPreviewTarget) generationPreviewActionTarget = null;
  updateGenerationPreviewActionState?.();
}

function getGenerationActiveOutputSnapshot() {
  if (generationActiveOutputSnapshot?.view_url) return { ...generationActiveOutputSnapshot };
  if (generationSelectedOutputSnapshot?.view_url) return cloneGenerationOutputSnapshot(generationSelectedOutputSnapshot);
  return null;
}


function cloneGenerationOutputForLineage(item) {
  if (!item || typeof item !== 'object') return null;
  return {
    id: item.id || '',
    filename: item.filename || '',
    saved_filename: item.saved_filename || '',
    saved_path: item.saved_path || '',
    view_url: item.view_url || '',
    sidecar_path: item.sidecar_path || '',
  };
}

function ensureGenerationLineageEntry(item, patch={}) {
  const key = generationOutputKey(item);
  if (!key) return '';
  const existing = generationOutputLineageState.entries[key] || {};
  generationOutputLineageState.entries[key] = {
    key,
    output: cloneGenerationOutputForLineage(item) || existing.output || null,
    parentKey: patch.parentKey !== undefined ? patch.parentKey : (existing.parentKey || ''),
    stage: patch.stage || existing.stage || '',
    jobId: patch.jobId || existing.jobId || '',
    createdAt: patch.createdAt || existing.createdAt || Date.now(),
    children: Array.isArray(existing.children) ? existing.children.slice() : [],
    imported: !!(patch.imported || existing.imported || item?.imported),
  };
  return key;
}

function rememberGenerationLineageHint(jobId, parentOutput, stage) {
  const target = String(jobId || '').trim();
  const parentKey = generationOutputKey(parentOutput);
  if (!target || !parentKey) return;
  ensureGenerationLineageEntry(parentOutput);
  const normalizedStage = String(stage || '').trim() || 'Derived pass';
  generationOutputLineageState.pendingJobs[target] = {
    parentKey,
    stage: normalizedStage,
    beforeUrl: String(parentOutput?.view_url || '').trim(),
    createdAt: Date.now(),
  };
  generationLastCompareBeforeUrl = String(parentOutput?.view_url || '').trim();
  generationLastCompareAfterUrl = '';
  generationPendingDerivedFocus = {
    jobId: target,
    parentKey,
    stage: normalizedStage,
    requestedAt: Date.now(),
    childKeys: [],
  };
}

function ingestGenerationJobIntoLineage(job) {
  const outputs = Array.isArray(job?.outputs) ? job.outputs : [];
  if (!outputs.length) return;
  const jobId = String(job?.id || '').trim();
  const hint = generationOutputLineageState.pendingJobs[jobId] || null;
  const childKeys = [];
  outputs.forEach(output => {
    const childKey = ensureGenerationLineageEntry(output, {
      parentKey: hint?.parentKey || '',
      stage: hint?.stage || '',
      jobId,
      createdAt: Date.now(),
    });
    if (hint?.parentKey && childKey) {
      const childEntry = generationOutputLineageState.entries[childKey] || null;
      if (childEntry) {
        const parentOutput = generationOutputLineageState.entries[hint.parentKey]?.output || null;
        childEntry.output = {
          ...(childEntry.output || {}),
          before_view_url: String(hint.beforeUrl || parentOutput?.view_url || '').trim(),
          source_view_url: String(hint.beforeUrl || parentOutput?.view_url || '').trim(),
          derived_from_output_id: hint.parentKey,
          derived_from_job_id: hint.parentKey ? (generationOutputLineageState.entries[hint.parentKey]?.jobId || '') : '',
          stage: hint.stage || childEntry.stage || '',
        };
        generationLastCompareBeforeUrl = childEntry.output.before_view_url || generationLastCompareBeforeUrl;
        generationLastCompareAfterUrl = String(childEntry.output.view_url || output?.view_url || '').trim();
        generationOutputLineageState.entries[childKey] = childEntry;
      }
      childKeys.push(childKey);
      const parent = generationOutputLineageState.entries[hint.parentKey] || null;
      if (parent) {
        const nextChildren = new Set(Array.isArray(parent.children) ? parent.children : []);
        nextChildren.add(childKey);
        parent.children = Array.from(nextChildren);
        generationOutputLineageState.entries[hint.parentKey] = parent;
      }
    }
  });
  if (hint) delete generationOutputLineageState.pendingJobs[jobId];
  if (generationPendingDerivedFocus && generationPendingDerivedFocus.jobId === jobId) {
    generationPendingDerivedFocus = {
      ...generationPendingDerivedFocus,
      childKeys: childKeys.slice(),
      resolvedAt: Date.now(),
    };
  }
}

function getGenerationLineageForOutput(item) {
  const key = generationOutputKey(item);
  if (!key) return { chain: [], children: [] };
  ensureGenerationLineageEntry(item);
  const visited = new Set();
  const chain = [];
  let cursor = generationOutputLineageState.entries[key] || null;
  while (cursor && cursor.key && !visited.has(cursor.key)) {
    visited.add(cursor.key);
    chain.unshift(cursor);
    cursor = cursor.parentKey ? generationOutputLineageState.entries[cursor.parentKey] || null : null;
  }
  const current = generationOutputLineageState.entries[key] || null;
  const children = (Array.isArray(current?.children) ? current.children : [])
    .map(childKey => generationOutputLineageState.entries[childKey] || null)
    .filter(Boolean)
    .sort((a, b) => Number(a.createdAt || 0) - Number(b.createdAt || 0));
  return { chain, children };
}

function findGenerationLineageOutputByKey(key) {
  const entry = generationOutputLineageState.entries[String(key || '').trim()] || null;
  return entry?.output ? { ...entry.output } : null;
}

function normalizeGenerationPassTarget(value, fallback='both') {
  const key = String(value || fallback || 'both').trim().toLowerCase();
  return ['base', 'finish', 'both'].includes(key) ? key : String(fallback || 'both');
}

function generationPassTargetLabel(value) {
  const key = normalizeGenerationPassTarget(value);
  if (key === 'base') return 'Base only';
  if (key === 'finish') return 'Finish only';
  return 'Both passes';
}

function renderGenerationOutputDetails(item) {
  const wrap = $('generation-output-details');
  if (!wrap) return;
  if (!item) {
    wrap.innerHTML = '';
    return;
  }
  const sourceName = item.saved_filename || item.filename || 'output';
  const savePath = item.saved_path || '';
  const sidecar = item.sidecar_path || '';
  wrap.innerHTML = `
    <div class="mini-note">${escapeHtml(sourceName)}</div>
    ${savePath ? `<div class="mini-note generation-path-chip">${escapeHtml(savePath)}</div>` : ''}
    ${sidecar ? `<div class="mini-note generation-path-chip">sidecar: ${escapeHtml(sidecar)}</div>` : ''}
  `;
}

function getGenerationFinishFoundationState() {
  return window.NeoGenerationResultsShell.getGenerationFinishFoundationState.apply(this, arguments);
}

function renderGenerationFinishFoundation() {
  return window.NeoGenerationResultsShell.renderGenerationFinishFoundation.apply(this, arguments);
}

function activateGenerationOutput(item, { openZoom=false, label='Latest final output' } = {}) {
  if (!item?.view_url) return;
  const itemKey = ensureGenerationLineageEntry(item, { imported: !!item?.imported });
  const lineageOutput = itemKey ? (generationOutputLineageState.entries[itemKey]?.output || null) : null;
  const enrichedItem = lineageOutput ? { ...item, ...lineageOutput } : item;
  const active = setGenerationActiveOutputSnapshot(enrichedItem, { syncPreviewTarget:true }) || cloneGenerationOutputSnapshot(enrichedItem) || { ...enrichedItem };
  showGenerationLivePreview(active.view_url, label);
  renderGenerationOutputDetails(active);
  renderGenerationFinishFoundation();
  const img = $('generation-live-preview');
  if (img) img.classList.toggle('is-batch', !!item.__batch);
  window.dispatchEvent(new CustomEvent('neo:generation-output-selected', {
    detail: {
      output: active,
      job: generationLatestJobSnapshot,
      label,
      openZoom: !!openZoom,
    }
  }));
  if (openZoom) openGenerationZoomModal();
}

function renderGenerationResults(job) {
  return window.NeoGenerationResultsShell.renderGenerationResults.apply(this, arguments);
}

function persistGenerationRecentRuns() {
  try { localStorage.setItem(generationRecentRunsStorageKey, JSON.stringify(generationRecentRuns || [])); } catch (_) {}
}

function loadGenerationRecentRuns() {
  try {
    const raw = localStorage.getItem(generationRecentRunsStorageKey);
    const parsed = raw ? JSON.parse(raw) : [];
    generationRecentRuns = Array.isArray(parsed) ? parsed.slice(0, 12) : [];
  } catch (_) {
    generationRecentRuns = [];
  }
}

function generationHistoryEntryLabel(entry) {
  if (!entry) return 'Recent run';
  const payload = entry.payload || {};
  const mode = entry.mode || payload.mode || payload.workflow_type || 'workflow';
  const size = payload.width && payload.height ? `${payload.width}×${payload.height}` : 'size ?';
  const seed = payload.seed ? `seed ${payload.seed}` : 'seed ?';
  const stamp = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }) : '';
  return [stamp, mode, size, seed].filter(Boolean).join(' · ');
}

function renderGenerationHistoryPanel() {
  const select = $('generation-history-select');
  const note = $('generation-history-note');
  const badge = $('generation-history-badge');
  if (!select || !note || !badge) return;
  const current = String(select.value || '');
  select.innerHTML = '';
  if (!generationRecentRuns.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No recent runs yet';
    select.appendChild(opt);
    badge.textContent = 'History idle';
    note.textContent = 'Rerun or restore a recent payload quickly, then use the hotkeys when you want less clicking.';
    return;
  }
  generationRecentRuns.forEach((entry, index) => {
    const opt = document.createElement('option');
    opt.value = String(entry.history_id || index);
    opt.textContent = generationHistoryEntryLabel(entry);
    if (current && current === opt.value) opt.selected = true;
    select.appendChild(opt);
  });
  if (!select.value && select.options.length) select.value = select.options[0].value;
  badge.textContent = `${generationRecentRuns.length} saved`;
  note.textContent = 'Ctrl/Cmd+Enter reruns the current workspace. Ctrl/Cmd+Shift+Enter queues without opening live watch. Restore selected pulls the payload back into the workspace first.';
}

function recordGenerationRecentRun(job) {
  const payload = job && typeof job.payload === 'object' && job.payload ? JSON.parse(JSON.stringify(job.payload)) : null;
  if (!payload) return;
  const historyId = String(job.prompt_id || job.id || `${payload.seed || 'seed'}-${payload.width || '?'}x${payload.height || '?'}`);
  const entry = {
    history_id: historyId,
    timestamp: Date.now(),
    mode: String(job.mode || payload.mode || payload.workflow_type || 'workflow'),
    prompt_id: String(job.prompt_id || ''),
    job_id: String(job.id || ''),
    payload,
  };
  generationRecentRuns = [entry].concat((generationRecentRuns || []).filter(item => String(item.history_id || '') !== historyId)).slice(0, 12);
  persistGenerationRecentRuns();
  renderGenerationHistoryPanel();
}

function getSelectedGenerationHistoryEntry() {
  const wanted = String($('generation-history-select')?.value || '');
  return (generationRecentRuns || []).find(item => String(item.history_id || '') === wanted) || generationRecentRuns[0] || null;
}

async function runGenerationHistoryEntry(entry, { watch=true } = {}) {
  if (!entry?.payload) {
    announceGenerationStatus('No recent payload is available yet.', 'warn');
    return false;
  }
  applyGenerationDraft({ ...(collectGenerationDraft() || {}), ...(entry.payload || {}) });
  const queued = await queueGenerationShell({ watch: !!watch, overridePayload: entry.payload, suppressInitialStatus:true });
  if (!queued) return false;
  announceGenerationStatus(watch ? 'Reran the selected payload.' : 'Queued the selected payload without live watch.', 'success');
  return true;
}

function restoreGenerationHistoryEntry(entry) {
  if (!entry?.payload) {
    announceGenerationStatus('Pick a recent payload first.', 'warn');
    return false;
  }
  applyGenerationDraft({ ...(collectGenerationDraft() || {}), ...(entry.payload || {}) });
  announceGenerationStatus('Restored the selected payload into the current workspace.', 'success');
  return true;
}

function renderGenerationJob(job) {
  if (!job) return;
  recordGenerationRecentRun(job);
  ingestGenerationJobIntoLineage(job);
  generationLatestJobSnapshot = job ? JSON.parse(JSON.stringify(job)) : null;
  lastGenerationJobId = job.id || lastGenerationJobId || '';
  if ($('generation-last-job-summary')) $('generation-last-job-summary').textContent = `${job.state || 'unknown'}${job.prompt_id ? ` · ${job.prompt_id}` : ''}`;
  if ($('generation-queue-summary')) $('generation-queue-summary').textContent = job.status_text || job.state || 'Queued';
  if ($('generation-payload-summary')) $('generation-payload-summary').textContent = `${job.mode || 'workflow'} · ${job.payload?.width || '?'}×${job.payload?.height || '?'} · ${job.payload?.sampler || 'sampler'} / ${job.payload?.scheduler || 'scheduler'} · seed ${job.payload?.seed || '?'}`;
  if ($('generation-preview-state')) $('generation-preview-state').textContent = job.error ? `${job.status_text || 'Error'} · ${job.error}` : (job.status_text || 'Queued in ComfyUI.');
  const state = String(job.state || '').toLowerCase();
  const finalizingStates = ['finalizing_output', 'outputs_registered', 'persisting_outputs'];
  const failureStates = ['error', 'failed'];
  const chipText = state === 'completed' ? 'Completed' : failureStates.includes(state) ? 'Error' : state === 'cancelled' ? 'Interrupted' : ['queued', 'pending'].includes(state) ? 'Queued' : ['running', 'processing', 'executing'].includes(state) ? 'Running' : finalizingStates.includes(state) ? 'Finalizing' : 'Monitoring';
  const chipTone = state === 'completed' ? 'success' : failureStates.includes(state) ? 'error' : state === 'cancelled' ? 'paused' : ['queued', 'pending', 'running', 'processing', 'executing', ...finalizingStates].includes(state) ? 'running' : 'idle';
  syncGenerationActionZoneMeta({
    stateText: chipText,
    stateTone: chipTone,
    modeText: generationActionModeLabel(job.mode || $('generation-workflow-type')?.value || 'txt2img'),
    queueText: job.status_text || job.state || 'Queued',
    jobText: `${job.state || 'unknown'}${job.prompt_id ? ` · ${job.prompt_id}` : ''}`,
    payloadText: `${job.payload?.width || '?'}×${job.payload?.height || '?'} · seed ${job.payload?.seed || '?'}`,
  });
  if ($('generation-progress-job-id')) $('generation-progress-job-id').textContent = job.prompt_id ? `Prompt ${job.prompt_id}` : (job.id ? `Job ${String(job.id).slice(0, 10)}` : 'Job —');
  if (state === 'completed') setGenerationProgress(100, 'Completed', 'ETA 00:00');
  else if (failureStates.includes(state)) setGenerationProgress(100, 'Generation failed', 'ETA —');
  else if (state === 'cancelled') resetGenerationProgress('Interrupted');
  else if (finalizingStates.includes(state)) setGenerationProgress(Math.max(95, Number(job?.progress?.percent || 95)), job.status_text || 'Finalizing output', 'ETA —');
  const firstSavedPath = Array.isArray(job.outputs) ? String(job.outputs.find(item => item && item.saved_path)?.saved_path || '') : '';
  if (firstSavedPath && $('generation-output-destination')) $('generation-output-destination').textContent = `Saved to: ${firstSavedPath}`;
  else updateGenerationOutputDestinationPreview(trim(job.payload?.seed || $('generation-seed')?.value || '') || '[seed]');
  renderGenerationResults(job);
  try { updateGenerationPreviewActionState?.(); } catch (_) {}
  window.dispatchEvent(new CustomEvent('neo:generation-job-updated', { detail: { job: generationLatestJobSnapshot } }));
}

function stopGenerationPolling() {
  if (generationPollTimer) {
    window.clearTimeout(generationPollTimer);
    generationPollTimer = null;
  }
  generationActivePollJobId = '';
}

async function fetchGenerationJob(jobId, { silent=false } = {}) {
  const target = String(jobId || '').trim();
  if (!target) return null;
  try {
    const data = await safeFetchJson(`/api/generation/job/${encodeURIComponent(target)}?_=${Date.now()}`, { cache:'no-store' });
    const job = data.job || null;
    if (job) renderGenerationJob(job);
    return job;
  } catch (e) {
    if (!silent) setStatus('generation-status', e.message || 'Could not load generation job state.', 'error');
    return null;
  }
}

function pollGenerationJob(jobId, options={}) {
  return window.NeoGenerationResultsShell.pollGenerationJob.apply(this, arguments);
}

async function refreshGenerationCatalog(force=false) {
  return window.NeoGenerationResultsShell.refreshGenerationCatalog.apply(this, arguments);
}

function selectedNodeManagerEntry() {
  const selected = trim($('node-manager-node-select')?.value || '');
  return nodeManagerNodes.find(row => String(row.folder_name || '') === selected) || null;
}

function renderNodeManagerSelectedDetails() {
  const box = $('node-manager-node-details');
  if (!box) return;
  const node = selectedNodeManagerEntry();
  if (!node) {
    box.innerHTML = 'Pick a node to inspect its repo details.';
    return;
  }
  box.innerHTML = `
    <div><strong>${escapeHtml(node.name || node.folder_name || 'custom node')}</strong></div>
    <div class="mini-note" style="margin-top:6px;">${escapeHtml(node.path || '')}</div>
    <div class="mini-note" style="margin-top:6px;">Git: ${node.is_git ? 'Yes' : 'No'}${node.branch ? ` · branch ${escapeHtml(node.branch)}` : ''}${node.commit ? ` · ${escapeHtml(node.commit)}` : ''}</div>
    <div class="mini-note" style="margin-top:6px;">Requirements: ${node.has_requirements ? 'requirements.txt found' : 'No requirements.txt'}</div>
    ${node.remote_url ? `<div class="mini-note" style="margin-top:6px;">Remote: ${escapeHtml(node.remote_url)}</div>` : ''}
    <div class="mini-note" style="margin-top:6px;">Last modified: ${escapeHtml(node.last_modified || '')}</div>
  `;
}

function renderNodeManagerState(data={}) {
  if ($('node-manager-custom-nodes-path')) $('node-manager-custom-nodes-path').value = data?.settings?.custom_nodes_path || $('node-manager-custom-nodes-path').value || '';
  if ($('node-manager-python-executable')) $('node-manager-python-executable').value = data?.settings?.python_executable || $('node-manager-python-executable').value || '';
  if ($('node-manager-log')) $('node-manager-log').value = data?.last_log || $('node-manager-log').value || '';
  nodeManagerNodes = Array.isArray(data?.nodes) ? data.nodes.slice() : [];
  const select = $('node-manager-node-select');
  if (select) {
    const current = trim(select.value || '');
    select.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = nodeManagerNodes.length ? 'Select an installed custom node…' : 'No custom nodes found';
    select.appendChild(placeholder);
    nodeManagerNodes.forEach(node => {
      const opt = document.createElement('option');
      opt.value = node.folder_name || '';
      opt.textContent = `${node.folder_name || 'custom node'}${node.branch ? ` · ${node.branch}` : ''}`;
      if (current && current === opt.value) opt.selected = true;
      select.appendChild(opt);
    });
    if (current && Array.from(select.options).some(opt => opt.value === current)) select.value = current;
  }
  const backend = data?.backend_session || {};
  const exists = !!data?.custom_nodes_path_exists;
  if ($('node-manager-summary')) $('node-manager-summary').textContent = `${nodeManagerNodes.length} installed node${nodeManagerNodes.length === 1 ? '' : 's'} · custom_nodes ${exists ? 'found' : 'missing'} · image backend ${backend.connected ? 'connected' : 'offline'}`;
  renderNodeManagerSelectedDetails();
}

async function fetchNodeManagerState(silent=false) {
  try {
    const data = await safeFetchJson(`/api/node-manager/state?_=${Date.now()}`, { cache:'no-store' });
    renderNodeManagerState(data || {});
    if (!silent) setStatus('node-manager-status', 'Node manager refreshed.', 'success');
    return data;
  } catch (e) {
    if (!silent) setStatus('node-manager-status', e.message || 'Could not load node manager state.', 'error');
    return null;
  }
}

async function saveNodeManagerSettingsUI() {
  const payload = {
    custom_nodes_path: $('node-manager-custom-nodes-path')?.value || '',
    python_executable: $('node-manager-python-executable')?.value || '',
  };
  try {
    const data = await safeFetchJson('/api/node-manager/settings-save', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify(payload),
    });
    renderNodeManagerState(data || {});
    setStatus('node-manager-status', data?.message || 'Node manager settings saved.', 'success');
  } catch (e) {
    setStatus('node-manager-status', e.message || 'Could not save node manager settings.', 'error');
  }
}

async function installNodeManagerRepo() {
  const gitUrl = trim($('node-manager-git-url')?.value || '');
  const branch = trim($('node-manager-git-branch')?.value || '');
  if (!gitUrl) {
    setStatus('node-manager-status', 'Paste a Git URL first.', 'warn');
    return;
  }
  const btn = $('btn-node-manager-install');
  const prev = btn?.textContent || 'Install Node';
  if (btn) { btn.setAttribute('disabled', 'disabled'); btn.textContent = 'Installing…'; }
  try {
    const data = await safeFetchJson('/api/node-manager/install', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ git_url: gitUrl, branch }),
    });
    renderNodeManagerState(data || {});
    if ($('node-manager-git-url')) $('node-manager-git-url').value = '';
    if ($('node-manager-git-branch')) $('node-manager-git-branch').value = '';
    setStatus('node-manager-status', data?.message || 'Custom node installed.', 'success');
  } catch (e) {
    setStatus('node-manager-status', e.message || 'Could not install the custom node.', 'error');
  } finally {
    if (btn) { btn.removeAttribute('disabled'); btn.textContent = prev; }
  }
}

async function updateSelectedNodeManagerRepo() {
  const selected = trim($('node-manager-node-select')?.value || '');
  if (!selected) {
    setStatus('node-manager-status', 'Pick an installed node first.', 'warn');
    return;
  }
  const btn = $('btn-node-manager-update-selected');
  const prev = btn?.textContent || 'Update Selected';
  if (btn) { btn.setAttribute('disabled', 'disabled'); btn.textContent = 'Updating…'; }
  try {
    const data = await safeFetchJson('/api/node-manager/update', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ folder_name: selected }),
    });
    renderNodeManagerState(data || {});
    if ($('node-manager-node-select')) $('node-manager-node-select').value = selected;
    renderNodeManagerSelectedDetails();
    setStatus('node-manager-status', data?.message || 'Custom node updated.', 'success');
  } catch (e) {
    setStatus('node-manager-status', e.message || 'Could not update the selected node.', 'error');
  } finally {
    if (btn) { btn.removeAttribute('disabled'); btn.textContent = prev; }
  }
}

async function openNodeManagerFolder(selectedOnly=false) {
  const folderName = selectedOnly ? trim($('node-manager-node-select')?.value || '') : '';
  try {
    const data = await safeFetchJson('/api/node-manager/open-folder', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ folder_name: folderName }),
    });
    renderNodeManagerState(data || {});
    setStatus('node-manager-status', data?.message || 'Folder opened.', 'success');
  } catch (e) {
    setStatus('node-manager-status', e.message || 'Could not open the folder.', 'error');
  }
}

async function reconnectNodeManagerImageBackend() {
  const btn = $('btn-node-manager-reconnect-image');
  const prev = btn?.textContent || 'Reconnect Image Backend';
  if (btn) { btn.setAttribute('disabled', 'disabled'); btn.textContent = 'Reconnecting…'; }
  try {
    const data = await safeFetchJson('/api/node-manager/reconnect-image-backend', { method:'POST' });
    renderNodeManagerState(data || {});
    setStatus('node-manager-status', data?.message || 'Image backend refresh finished.', data?.ok === false ? 'warn' : 'success');
  } catch (e) {
    setStatus('node-manager-status', e.message || 'Could not refresh the image backend.', 'error');
  } finally {
    if (btn) { btn.removeAttribute('disabled'); btn.textContent = prev; }
  }
}



function extractGenerationDependencyDraft(draft={}) {
  const source = draft && typeof draft === 'object' ? draft : {};
  return {
    checkpoint: source.checkpoint || '',
    vae: source.vae || '',
    refine_enabled: source.refine_enabled || 'false',
    refine_mode: source.refine_mode || 'latent',
    refine_upscaler: source.refine_upscaler || '',
    supir_enabled: source.supir_enabled || 'false',
    supir_model: source.supir_model || '',
    supir_sdxl_model: source.supir_sdxl_model || '',
    detailer_enabled: !!source.detailer_enabled,
    detailer_detector_type: source.detailer_detector_type || 'bbox',
    detailer_model: source.detailer_model || '',
    detailer_sam_model: source.detailer_sam_model || '',
    detailer_custom_detector_root: source.detailer_custom_detector_root || '',
    detailer_custom_sam_root: source.detailer_custom_sam_root || '',
    detailer_passes: Array.isArray(source.detailer_passes) ? source.detailer_passes.map(item => ({
      enabled: !!item?.enabled,
      detector_type: item?.detector_type || 'bbox',
      detector_model: item?.detector_model || '',
      sam_model: item?.sam_model || '',
    })) : [],
    loras: Array.isArray(source.loras) ? source.loras.map(item => ({ enabled: !!item?.enabled, name: item?.name || '' })) : [],
    controlnet_enabled: !!source.controlnet_enabled,
    controlnet_name: source.controlnet_name || '',
    controlnet_units: Array.isArray(source.controlnet_units) ? source.controlnet_units.map(item => ({ enabled: !!item?.enabled, model: item?.model || '' })) : [],
    ipadapter_enabled: !!source.ipadapter_enabled,
    ipadapter_mode: source.ipadapter_mode || 'standard',
    ipadapter_name: source.ipadapter_name || '',
    ipadapter_clip_vision: source.ipadapter_clip_vision || '',
    ipadapter_units: Array.isArray(source.ipadapter_units) ? source.ipadapter_units.map(item => ({
      enabled: !!item?.enabled,
      mode: item?.mode || 'standard',
      model: item?.model || '',
      clip_vision: item?.clip_vision || '',
    })) : [],
  };
}

async function fetchGenerationDependencyAudit(options={}) {
  const imageSession = getRoleSession('image');
  if (!imageSession.connected) {
    generationDependencyAuditState = { ok:false, issues:[], summary:{}, yaml:{ active:false, files:[], paths_by_category:{} }, checked_nodes:[], checked_models:[] };
    generationDependencyAuditCacheKey = '';
    generationDependencyAuditCacheAt = 0;
    window.dispatchEvent(new CustomEvent('neo:generation-dependency-audit-refreshed', { detail: generationDependencyAuditState }));
    return generationDependencyAuditState;
  }

  const draft = extractGenerationDependencyDraft(options?.draft || collectGenerationDraft());
  const cacheKey = JSON.stringify(draft);
  const now = Date.now();
  if (!options?.force && generationDependencyAuditCacheKey === cacheKey && (now - generationDependencyAuditCacheAt) < 4000 && generationDependencyAuditState?.ok) {
    return generationDependencyAuditState;
  }

  try {
    const data = await safeFetchJson('/api/generation/dependency-audit', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ draft }),
    });
    generationDependencyAuditState = (data && typeof data === 'object') ? data : { ok:false, issues:[], summary:{}, yaml:{ active:false, files:[], paths_by_category:{} }, checked_nodes:[], checked_models:[] };
    generationDependencyAuditCacheKey = cacheKey;
    generationDependencyAuditCacheAt = now;
    window.dispatchEvent(new CustomEvent('neo:generation-dependency-audit-refreshed', { detail: generationDependencyAuditState }));
    return generationDependencyAuditState;
  } catch (e) {
    generationDependencyAuditState = { ok:false, error: e?.message || 'Could not load dependency audit.', issues:[], summary:{}, yaml:{ active:false, files:[], paths_by_category:{} }, checked_nodes:[], checked_models:[] };
    window.dispatchEvent(new CustomEvent('neo:generation-dependency-audit-refreshed', { detail: generationDependencyAuditState }));
    if (!options?.silent) setStatus('generation-status', e.message || 'Could not load dependency audit.', 'error');
    return generationDependencyAuditState;
  }
}

async function fetchGenerationState(silent=false) {
  try {
    const state = await safeFetchJson('/api/generation/state?limit=12');
    const jobs = state.jobs || [];
    const activeId = String(generationActivePollJobId || lastGenerationJobId || '').trim();
    let latestJob = activeId ? (jobs.find(job => String(job?.id || '') === activeId) || null) : null;
    if (!latestJob) latestJob = jobs.length ? jobs[0] : null;
    if (latestJob) {
      const hydrated = await fetchGenerationJob(latestJob.id, { silent:true });
      if (hydrated) latestJob = hydrated;
      else renderGenerationJob(latestJob);
      const latestState = String(latestJob?.state || '').toLowerCase();
      // Only let the state refresh own polling for the selected/latest run.
      // Older stuck jobs may still be refreshed by the backend, but they should
      // not steal the preview/results panel from the batch that just completed.
      if (latestJob?.id && !['completed', 'error', 'failed', 'cancelled'].includes(latestState)) pollGenerationJob(latestJob.id);
      else if (!generationActivePollJobId || String(generationActivePollJobId) === String(latestJob?.id || '')) stopGenerationPolling();
    } else {
      stopGenerationPolling();
      closeGenerationProgressSocket();
      resetGenerationProgress('Idle');
      if ($('generation-last-job-summary')) $('generation-last-job-summary').textContent = 'No job yet';
      syncGenerationActionZoneFromShell();
    }
    if (!latestJob) syncGenerationActionZoneFromShell();
    if (!silent) setStatus('generation-status', jobs.length ? 'Generation state refreshed.' : 'No generation jobs yet.');
  } catch (e) {
    if (!silent) setStatus('generation-status', e.message || 'Could not load generation state.', 'error');
  }
}

async function refreshGenerationBackendState() {
  try {
    if (typeof fetchBackendManagerState === 'function') await fetchBackendManagerState({ silent:true });
    await refreshGenerationCatalog(true);
    await fetchGenerationState(true);
    syncGenerationActionZoneFromShell();
    setStatus('generation-status', 'Generation backend state refreshed.');
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not refresh backend state.', 'error');
  }
}

async function copyGenerationPayload() {
  const payload = buildGenerationPayload();
  try {
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    if ($('generation-payload-summary')) $('generation-payload-summary').textContent = 'Payload copied to clipboard';
    syncGenerationActionZoneFromShell();
    setStatus('generation-status', 'Generation payload copied as JSON.');
  } catch (e) {
    setStatus('generation-status', 'Could not copy the generation payload.', 'error');
  }
}


// Phase 9.2 compatibility override: Regional Prompter has been removed, but this
// legacy mixed module still gets loaded by the Image tab. Keep the non-regional
// helpers above available, then force every regional contract entry point to a
// harmless disabled shape so generation/backend catalog loading cannot crash.
function getGenerationRegionalComposerMode() { return 'removed'; }
function getGenerationRegionalBackendMode() { return 'removed'; }
function getGenerationRegionalBackendCapabilities() { return {}; }
function getGenerationRegionalDisplayMode() { return 'auto'; }
function getGenerationRegionalResolvedDisplayMode() { return 'boxes'; }
function getGenerationRegionalCount() { return 0; }
function getGenerationRegionalPaintSoftness() { return 0; }
function getGenerationRegionalPainterMode() { return 'off'; }
function getGenerationRegionalPainterBrush() { return 0; }
function getGenerationRegionalEffectiveStateSnapshot() {
  return {
    enabledRoot: false,
    composerMode: 'removed',
    regionCount: 0,
    hasSolo: false,
    regions: [],
    effectiveIndices: [],
  };
}
function collectGenerationRegionalPromptSettings() {
  return {
    regional_prompt_enabled: false,
    regional_prompt_profile: 'removed',
    regional_composer_mode: 'removed',
    regional_backend_mode: 'removed',
    regional_backend_capabilities: {},
    regional_overlap_mode: 'none',
    regional_count: 0,
    regional_prompt_regions: [],
  };
}
function syncGenerationRegionalPromptUI() { return collectGenerationRegionalPromptSettings(); }
function applyGenerationRegionalPromptProfile() { return collectGenerationRegionalPromptSettings(); }
function applyGenerationRegionalCountLayout() { return collectGenerationRegionalPromptSettings(); }
function setGenerationRegionalCount() { return collectGenerationRegionalPromptSettings(); }
function stepGenerationRegionalCount() { return collectGenerationRegionalPromptSettings(); }
function bindGenerationRegionalDynamicListeners() {}
function renderGenerationRegionalCanvas() {}
function beginGenerationRegionalPainter() {}
function handleGenerationRegionalCanvasMove() {}
function handleGenerationRegionalPainterMove() {}
function endGenerationRegionalCanvasMove() {}
function endGenerationRegionalPainter() {}
function clearGenerationRegionalPaintMask() {}
async function applyGenerationRegionalPaintMask() { return null; }
async function prepareGenerationRegionalMaskUploads() { return {}; }
