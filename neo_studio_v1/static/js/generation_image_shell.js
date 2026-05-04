window.NeoGenerationImageShell = window.NeoGenerationImageShell || {};

window.NeoGenerationImageShell.renderGenerationImagePreflight = function renderGenerationImagePreflight() {
  const summary = $('generation-preflight-summary');
  const strip = $('generation-preflight-strip');
  const warning = $('generation-preflight-warning');
  const badge = $('generation-preflight-badge');
  if (!summary || !strip || !warning || !badge) return;
  const sourceW = Number(generationSourceImageInfo.width || 0) || 0;
  const sourceH = Number(generationSourceImageInfo.height || 0) || 0;
  const targetW = Number($('generation-width')?.value || 0) || 0;
  const targetH = Number($('generation-height')?.value || 0) || 0;
  const resizeMode = String($('generation-source-resize-mode')?.value || 'native').trim() || 'native';
  if (!(sourceW > 0 && sourceH > 0)) {
    badge.textContent = 'Idle';
    badge.classList.remove('ok');
    summary.textContent = 'Load a source image to compare it against the current target size.';
    strip.innerHTML = '<span class="badge">No source image</span>';
    warning.textContent = 'Neo will suggest fit, crop, or outpaint based on the current source/target mismatch.';
    return;
  }
  const sourceRatio = sourceW / Math.max(1, sourceH);
  const targetRatio = targetW > 0 && targetH > 0 ? (targetW / Math.max(1, targetH)) : sourceRatio;
  const ratioDelta = Math.abs(sourceRatio - targetRatio);
  const exactSize = sourceW === targetW && sourceH === targetH && targetW > 0 && targetH > 0;
  const smallerThanTarget = targetW > 0 && targetH > 0 && (sourceW < targetW || sourceH < targetH);
  const largerThanTarget = targetW > 0 && targetH > 0 && (sourceW > targetW || sourceH > targetH);
  const heavyMismatch = ratioDelta > 0.12;
  const moderateMismatch = ratioDelta > 0.04;
  let state = 'Ready';
  let recommendation = exactSize
    ? 'Source already matches the target. You can route it directly into img2img, ControlNet, or Finish.'
    : 'Source and target differ. Fit, crop, or outpaint based on how much composition you need to preserve.';
  if (resizeMode === 'crop' && targetW > 0 && targetH > 0) {
    recommendation = `Neo will center-crop + resize the source to ${targetW}×${targetH} when you queue the run.`;
  } else if (resizeMode === 'fit' && targetW > 0 && targetH > 0) {
    recommendation = `Neo will fit the source inside ${targetW}×${targetH} and pad the frame instead of stretching it.`;
  } else if (resizeMode === 'stretch' && targetW > 0 && targetH > 0) {
    recommendation = `Neo will force-resize the source to ${targetW}×${targetH}, so aspect distortion is expected.`;
  }
  if (heavyMismatch) {
    state = 'Watch';
    recommendation = resizeMode === 'crop' && targetW > 0 && targetH > 0
      ? `Aspect mismatch is large. Neo will center-crop + resize the source to ${targetW}×${targetH} at queue time.`
      : 'Aspect mismatch is large. Crop or outpaint will usually behave better than stretch.';
  } else if (smallerThanTarget) {
    state = 'Watch';
    recommendation = resizeMode === 'crop' && targetW > 0 && targetH > 0
      ? `Source is smaller than the target, so crop mode will still upscale it to ${targetW}×${targetH}.`
      : 'Source is smaller than the current target. Fit or crop will upscale; outpaint or finish-upscale may be cleaner.';
  } else if (largerThanTarget && moderateMismatch) {
    state = 'Watch';
    recommendation = resizeMode === 'crop' && targetW > 0 && targetH > 0
      ? `Source is larger than the target and crop mode will trim it down to ${targetW}×${targetH}.`
      : 'Source is larger than target but aspect is off. Crop is usually cleaner than fit here.';
  }
  badge.textContent = state;
  badge.classList.toggle('ok', state === 'Ready');
  summary.textContent = `Source ${formatOutpaintSizeLabel(sourceW, sourceH)} → Target ${targetW > 0 && targetH > 0 ? formatOutpaintSizeLabel(targetW, targetH) : 'not set'} · resize ${resizeMode.replace('_', ' ')}`;
  const chips = [
    { text: `${sourceW}×${sourceH}`, ok:true },
    { text: targetW > 0 && targetH > 0 ? `${targetW}×${targetH}` : 'Target unset', ok: targetW > 0 && targetH > 0 },
    { text: `Resize ${resizeMode}`, ok: resizeMode !== 'stretch' },
  ];
  if (exactSize) chips.push({ text:'Exact size match', ok:true });
  else if (heavyMismatch) chips.push({ text:'Large aspect mismatch', ok:false });
  else if (moderateMismatch) chips.push({ text:'Aspect mismatch', ok:false });
  if (smallerThanTarget) chips.push({ text:'Source smaller than target', ok:false });
  if (largerThanTarget) chips.push({ text:'Source larger than target', ok:true });
  strip.innerHTML = chips.map(chip => `<span class="badge${chip.ok ? ' ok' : ''}">${escapeHtml(chip.text)}</span>`).join('');
  warning.textContent = recommendation;
}

window.NeoGenerationImageShell.openGenerationMaskEditor = async function openGenerationMaskEditor() {
  const sourceFile = $('generation-source-image')?.files?.[0] || null;
  if (!sourceFile) {
    setStatus('generation-status', 'Add a source image first, then open the mask editor.', 'warn');
    return;
  }
  try {
    const sourceImage = await loadFileAsImage(sourceFile);
    const existingMaskFile = $('generation-mask-image')?.files?.[0] || null;
    const modal = $('generation-mask-editor-modal');
    const baseCanvas = $('generation-mask-base-canvas');
    const drawCanvas = $('generation-mask-draw-canvas');
    if (!modal || !baseCanvas || !drawCanvas) return;
    const maxW = Math.min(window.innerWidth * 0.82, 980);
    const maxH = Math.min(window.innerHeight * 0.68, 700);
    const scale = Math.min(maxW / sourceImage.naturalWidth, maxH / sourceImage.naturalHeight, 1);
    const displayW = Math.max(64, Math.round(sourceImage.naturalWidth * scale));
    const displayH = Math.max(64, Math.round(sourceImage.naturalHeight * scale));
    baseCanvas.width = displayW; baseCanvas.height = displayH;
    drawCanvas.width = displayW; drawCanvas.height = displayH;
    baseCanvas.style.width = `${displayW}px`; baseCanvas.style.height = `${displayH}px`;
    drawCanvas.style.width = `${displayW}px`; drawCanvas.style.height = `${displayH}px`;
    const exportCanvas = document.createElement('canvas');
    exportCanvas.width = sourceImage.naturalWidth;
    exportCanvas.height = sourceImage.naturalHeight;
    generationMaskEditorState = {
      sourceImage,
      displayScale: scale,
      exportCanvas,
      drawing:false,
      lastPoint:null,
      brushMode:'paint',
      displayWidth:displayW,
      displayHeight:displayH,
      zoom:1,
      minZoom:1,
      maxZoom:8,
      panning:false,
      panLast:null,
      spaceDown:false,
    };
    const bctx = baseCanvas.getContext('2d');
    bctx.clearRect(0,0,displayW,displayH);
    bctx.drawImage(sourceImage, 0, 0, displayW, displayH);
    clearMaskPreviewCanvas(drawCanvas);
    fillMaskCanvasBlack(exportCanvas);
    if (existingMaskFile) {
      try {
        const maskImage = await loadFileAsImage(existingMaskFile);
        exportCanvas.getContext('2d').drawImage(maskImage, 0, 0, exportCanvas.width, exportCanvas.height);
      } catch (_) {}
    }
    syncMaskPreviewFromExport();
    updateMaskEditorZoomLabel();
    applyMaskEditorZoom(1);
    updateMaskBrushLabel();
    hideMaskBrushCursor();
    modal.classList.remove('hidden');
    document.body.classList.add('modal-open');
  } catch (e) {
    setStatus('generation-status', e.message || 'Could not open the mask editor.', 'error');
  }
}

