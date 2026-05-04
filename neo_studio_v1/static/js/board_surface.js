(function () {
  const API_ROOT = '/api/board/boards';
  const IMAGE_MEDIA_ROOT = '/api/board/media/images';
  const AUDIO_MEDIA_ROOT = '/api/board/media/audio';
  const VIDEO_MEDIA_ROOT = '/api/board/media/videos';
  const CARD_COLORS = ['gold', 'rose', 'mint', 'sky', 'slate'];
  const CARD_COLOR_HEX = {
    gold: '#facc15',
    rose: '#fb7185',
    mint: '#4ade80',
    sky: '#38bdf8',
    slate: '#94a3b8',
  };
  const state = {
    boards: [],
    currentBoard: null,
    loading: false,
    renaming: false,
    saveTimer: null,
    saving: false,
    dirty: false,
    selectedItemId: '',
    drag: null,
    resize: null,
    pan: null,
    spacePanning: false,
    changeVersion: 0,
    pendingSave: false,
    recoveryTimer: null,
    lastSavedAt: '',
    saveError: '',
    recorder: null,
    recorderChunks: [],
    recorderStream: null,
  };

  function $(id) { return document.getElementById(id); }

  function setStatus(text) {
    const el = $('board-save-status');
    if (el) el.textContent = text || '';
  }

  function setBadge(text) {
    const el = $('board-surface-state-badge');
    if (el) el.textContent = text || 'Ready';
  }


  function formatSavedTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function isRecoveryNewer(recovery, board) {
    if (!recovery || !recovery.board || !board) return false;
    const recoveryTime = Date.parse(recovery.saved_at || recovery.board.updated_at || '');
    const boardTime = Date.parse(board.updated_at || '');
    if (Number.isNaN(recoveryTime)) return false;
    if (Number.isNaN(boardTime)) return true;
    return recoveryTime > boardTime + 500;
  }

  function browserRecoveryKey(boardId) {
    return `neo_board_recovery_${boardId || 'unknown'}`;
  }

  function writeBrowserRecovery(board) {
    try {
      if (!board || !board.id) return;
      localStorage.setItem(browserRecoveryKey(board.id), JSON.stringify({ saved_at: new Date().toISOString(), board: cloneBoardForSave(board) }));
    } catch (_) {}
  }

  function clearBrowserRecovery(boardId) {
    try { if (boardId) localStorage.removeItem(browserRecoveryKey(boardId)); } catch (_) {}
  }

  function makeClientId(prefix) {
    if (window.crypto && window.crypto.randomUUID) return `${prefix}_${window.crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
    return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  }

  async function api(path, options) {
    const response = await fetch(path, Object.assign({
      headers: { 'Content-Type': 'application/json' },
    }, options || {}));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || payload.detail || 'Board request failed.');
    }
    return payload;
  }

  function ensureBoardShape(board) {
    if (!board) return null;
    if (!Array.isArray(board.items)) board.items = [];
    if (!board.canvas || typeof board.canvas !== 'object') board.canvas = {};
    ensureCanvasView(board);
    return board;
  }

  function ensureCanvasView(board) {
    const target = board || state.currentBoard;
    if (!target) return null;
    if (!target.canvas || typeof target.canvas !== 'object') target.canvas = {};
    const canvas = target.canvas;
    canvas.zoom = clampZoom(canvas.zoom);
    canvas.pan_x = sanitizeViewNumber(canvas.pan_x, 0);
    canvas.pan_y = sanitizeViewNumber(canvas.pan_y, 0);
    if (typeof canvas.grid_enabled !== 'boolean') canvas.grid_enabled = true;
    return canvas;
  }

  function sanitizeViewNumber(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function clampZoom(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 1;
    return Math.min(2.5, Math.max(0.25, number));
  }

  function getCanvasView() {
    return ensureCanvasView(state.currentBoard) || { zoom: 1, pan_x: 0, pan_y: 0, grid_enabled: true };
  }

  function getCanvasZoom() {
    return clampZoom(getCanvasView().zoom);
  }

  function renderCanvasView() {
    const canvas = $('board-canvas');
    const shell = canvas ? canvas.closest('.board-canvas-shell') : null;
    const view = getCanvasView();
    if (canvas) {
      canvas.style.transformOrigin = '0 0';
      canvas.style.transform = `translate(${Math.round(view.pan_x)}px, ${Math.round(view.pan_y)}px) scale(${view.zoom})`;
      canvas.classList.toggle('board-grid-off', !view.grid_enabled);
    }
    if (shell) {
      shell.dataset.panning = state.pan ? '1' : '0';
      shell.dataset.spacePanning = state.spacePanning ? '1' : '0';
    }
    const zoomLabel = $('board-zoom-label');
    if (zoomLabel) zoomLabel.textContent = `${Math.round(view.zoom * 100)}%`;
    const gridToggle = $('board-grid-toggle');
    if (gridToggle) {
      gridToggle.textContent = view.grid_enabled ? 'Grid On' : 'Grid Off';
      gridToggle.dataset.active = view.grid_enabled ? '1' : '0';
    }
  }

  function queueViewSave(message, delay) {
    renderCanvasView();
    queueSave(message || 'Board view updated…', Number.isFinite(delay) ? delay : 700);
  }

  function setCanvasZoom(nextZoom, anchor) {
    if (!state.currentBoard) return;
    const view = getCanvasView();
    const oldZoom = clampZoom(view.zoom);
    const zoom = clampZoom(nextZoom);
    if (Math.abs(zoom - oldZoom) < 0.001) return;
    const shell = $('board-canvas')?.closest('.board-canvas-shell');
    const rect = shell ? shell.getBoundingClientRect() : null;
    const anchorX = anchor?.x ?? (rect ? rect.width / 2 : 0);
    const anchorY = anchor?.y ?? (rect ? rect.height / 2 : 0);
    const boardX = (anchorX - view.pan_x) / oldZoom;
    const boardY = (anchorY - view.pan_y) / oldZoom;
    view.zoom = zoom;
    view.pan_x = Math.round(anchorX - boardX * zoom);
    view.pan_y = Math.round(anchorY - boardY * zoom);
    queueViewSave('Zoom updated…');
  }

  function resetCanvasView() {
    if (!state.currentBoard) return;
    const view = getCanvasView();
    view.zoom = 1;
    view.pan_x = 0;
    view.pan_y = 0;
    queueViewSave('View reset…', 250);
  }

  function fitCanvasToContent() {
    if (!state.currentBoard) return;
    const shell = $('board-canvas')?.closest('.board-canvas-shell');
    const items = state.currentBoard.items || [];
    if (!shell || !items.length) {
      resetCanvasView();
      return;
    }
    const left = Math.min(...items.map((item) => Number(item.x || 0)));
    const top = Math.min(...items.map((item) => Number(item.y || 0)));
    const right = Math.max(...items.map((item) => Number(item.x || 0) + Number(item.w || 260)));
    const bottom = Math.max(...items.map((item) => Number(item.y || 0) + Number(item.h || 180)));
    const rect = shell.getBoundingClientRect();
    const contentW = Math.max(1, right - left);
    const contentH = Math.max(1, bottom - top);
    const zoom = clampZoom(Math.min((rect.width - 80) / contentW, (rect.height - 80) / contentH, 1));
    const view = getCanvasView();
    view.zoom = zoom;
    view.pan_x = Math.round((rect.width - contentW * zoom) / 2 - left * zoom);
    view.pan_y = Math.round((rect.height - contentH * zoom) / 2 - top * zoom);
    queueViewSave('Fit to content…', 250);
  }

  function toggleCanvasGrid() {
    if (!state.currentBoard) return;
    const view = getCanvasView();
    view.grid_enabled = !view.grid_enabled;
    queueViewSave(view.grid_enabled ? 'Grid enabled…' : 'Grid hidden…', 250);
  }

  function renderBoardPicker() {
    const picker = $('board-picker');
    if (!picker) return;
    picker.innerHTML = '';

    if (!state.boards.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No boards yet';
      picker.appendChild(option);
      picker.disabled = true;
      return;
    }

    picker.disabled = false;
    state.boards.forEach((board) => {
      const option = document.createElement('option');
      option.value = board.id;
      option.textContent = board.name || 'Untitled Board';
      picker.appendChild(option);
    });
    picker.value = state.currentBoard?.id || state.boards[0]?.id || '';
  }

  function renderCurrentBoard() {
    state.currentBoard = ensureBoardShape(state.currentBoard);
    const hasBoard = !!state.currentBoard;
    const nameInput = $('board-name-input');
    const canvas = $('board-canvas');
    if (canvas && !canvas.dataset.panBound) {
      canvas.dataset.panBound = '1';
      canvas.addEventListener('pointerdown', handleCanvasPointerDown);
      canvas.addEventListener('wheel', (event) => {
        if (!state.currentBoard || (!event.ctrlKey && !event.metaKey)) return;
        event.preventDefault();
        const shell = canvas.closest('.board-canvas-shell');
        const rect = shell ? shell.getBoundingClientRect() : { left: 0, top: 0 };
        const factor = event.deltaY < 0 ? 1.1 : 0.9;
        setCanvasZoom(getCanvasZoom() * factor, { x: event.clientX - rect.left, y: event.clientY - rect.top });
      }, { passive: false });
    }

    const zoomOutBtn = $('board-zoom-out');
    if (zoomOutBtn && !zoomOutBtn.dataset.bound) {
      zoomOutBtn.dataset.bound = '1';
      zoomOutBtn.addEventListener('click', () => setCanvasZoom(getCanvasZoom() / 1.15));
    }

    const zoomInBtn = $('board-zoom-in');
    if (zoomInBtn && !zoomInBtn.dataset.bound) {
      zoomInBtn.dataset.bound = '1';
      zoomInBtn.addEventListener('click', () => setCanvasZoom(getCanvasZoom() * 1.15));
    }

    const zoomResetBtn = $('board-zoom-reset');
    if (zoomResetBtn && !zoomResetBtn.dataset.bound) {
      zoomResetBtn.dataset.bound = '1';
      zoomResetBtn.addEventListener('click', resetCanvasView);
    }

    const fitBtn = $('board-fit-content');
    if (fitBtn && !fitBtn.dataset.bound) {
      fitBtn.dataset.bound = '1';
      fitBtn.addEventListener('click', fitCanvasToContent);
    }

    const gridBtn = $('board-grid-toggle');
    if (gridBtn && !gridBtn.dataset.bound) {
      gridBtn.dataset.bound = '1';
      gridBtn.addEventListener('click', toggleCanvasGrid);
    }

    const duplicateBtn = $('board-duplicate-btn');
    const deleteBtn = $('board-delete-btn');
    const addStickyBtn = $('board-add-sticky');
    const addChecklistBtn = $('board-add-checklist');
    const addTextBtn = $('board-add-text');
    const addImageBtn = $('board-add-image');
    const addAudioBtn = $('board-add-audio');
    const recordAudioBtn = $('board-record-audio');
    const addVideoBtn = $('board-add-video');
    const futureButtons = [];

    if (nameInput) {
      nameInput.disabled = !hasBoard;
      nameInput.value = hasBoard ? (state.currentBoard.name || 'Untitled Board') : '';
    }
    if (duplicateBtn) duplicateBtn.disabled = !hasBoard;
    if (deleteBtn) deleteBtn.disabled = !hasBoard;
    if (addStickyBtn) addStickyBtn.disabled = !hasBoard;
    if (addChecklistBtn) addChecklistBtn.disabled = !hasBoard;
    if (addTextBtn) addTextBtn.disabled = !hasBoard;
    if (addImageBtn) addImageBtn.disabled = !hasBoard;
    if (addAudioBtn) addAudioBtn.disabled = !hasBoard;
    if (recordAudioBtn) recordAudioBtn.disabled = !hasBoard || !supportsAudioRecording();
    if (addVideoBtn) addVideoBtn.disabled = !hasBoard;
    updateRecorderButton();
    futureButtons.forEach((id) => {
      const button = $(id);
      if (button) button.disabled = true;
    });

    renderBoardCanvas();
    renderCanvasView();
    setBadge(hasBoard ? (state.dirty ? 'Unsaved' : 'Ready') : 'No board');
    if (!state.dirty && !state.saving) setStatus(hasBoard ? `Loaded · ${state.currentBoard.items?.length || 0} items` : 'Choose or create a board');
    renderBoardPicker();
  }

  function renderBoardCanvas() {
    const canvas = $('board-canvas');
    if (!canvas) return;
    canvas.innerHTML = '';
    canvas.style.minWidth = '';
    canvas.style.minHeight = '';
    renderCanvasView();

    if (!state.currentBoard) {
      canvas.classList.remove('has-board', 'has-items');
      canvas.appendChild(buildEmptyState({
        title: 'Board shell is ready.',
        copy: 'Create or select a board above. Sticky notes, checklist cards, text layers, image cards, audio cards, and recorded voice notes, and video cards are available with freeform move/resize. Video cards are now available for local reference planning.',
        button: 'Create first board',
        disabled: false,
      }));
      return;
    }

    const boardItems = (state.currentBoard.items || []).filter((item) => item && ['sticky', 'checklist', 'text', 'image', 'audio', 'video'].includes(item.type));
    canvas.classList.add('has-board');
    canvas.classList.toggle('has-items', boardItems.length > 0);

    if (!boardItems.length) {
      canvas.appendChild(buildEmptyState({
        title: 'This board is empty.',
        copy: 'Add a sticky note, checklist, text layer, image card, audio card, or recorded voice note to start planning. Video cards are now available for local reference planning.',
        button: 'Add Sticky',
        disabled: false,
        action: createStickyNote,
      }));
      return;
    }

    applyCanvasBounds(canvas, boardItems);
    boardItems
      .slice()
      .sort((a, b) => Number(a.z || 0) - Number(b.z || 0))
      .forEach((item) => canvas.appendChild(buildBoardCard(item)));
  }

  function applyCanvasBounds(canvas, items) {
    const padding = 260;
    const maxRight = Math.max(900, ...items.map((item) => Number(item.x || 0) + Number(item.w || 260) + padding));
    const maxBottom = Math.max(680, ...items.map((item) => Number(item.y || 0) + Number(item.h || 180) + padding));
    canvas.style.minWidth = `${Math.ceil(maxRight)}px`;
    canvas.style.minHeight = `${Math.ceil(maxBottom)}px`;
  }

  function buildEmptyState(config) {
    const wrap = document.createElement('div');
    wrap.className = 'board-empty-state';
    wrap.id = 'board-empty-state';
    wrap.innerHTML = `
      <div class="badge">Canvas-first workspace</div>
      <h3></h3>
      <p class="muted"></p>
      <button class="btn" type="button" id="board-empty-create-btn"></button>
    `;
    wrap.querySelector('h3').textContent = config.title;
    wrap.querySelector('p').textContent = config.copy;
    const button = wrap.querySelector('button');
    button.textContent = config.button;
    button.disabled = !!config.disabled;
    button.addEventListener('click', () => {
      if (config.action) config.action();
      else createBoard('Untitled Board').catch((error) => setStatus(error.message));
    });
    return wrap;
  }

  function buildBoardCard(item) {
    let card;
    if (item.type === 'checklist') card = buildChecklistCard(item);
    else if (item.type === 'text') card = buildTextLayer(item);
    else if (item.type === 'image') card = buildImageCard(item);
    else if (item.type === 'audio') card = buildAudioCard(item);
    else if (item.type === 'video') card = buildVideoCard(item);
    else card = buildStickyCard(item);
    applyChecklistLinkedState(card, item);
    return card;
  }

  function buildStickyCard(item) {
    const card = document.createElement('article');
    card.className = `board-card board-sticky board-card-${normalizeCardColor(item.color)}`;
    applyCardColorStyle(card, item.color);
    card.dataset.itemId = item.id;
    card.dataset.selected = state.selectedItemId === item.id ? '1' : '0';
    card.style.left = `${Number(item.x || 120)}px`;
    card.style.top = `${Number(item.y || 120)}px`;
    card.style.width = `${Number(item.w || 260)}px`;
    card.style.height = `${Number(item.h || 180)}px`;
    card.style.zIndex = String(Number(item.z || 1));

    const header = document.createElement('div');
    header.className = 'board-card-header board-card-drag-handle';
    header.title = 'Drag to move';

    const title = document.createElement('input');
    title.className = 'board-card-title-input';
    title.type = 'text';
    title.maxLength = 120;
    title.value = item.title || 'Sticky note';
    title.placeholder = 'Sticky title';
    title.addEventListener('input', () => {
      item.title = title.value;
      queueSave('Editing sticky…');
    });

    const actions = document.createElement('div');
    actions.className = 'board-card-actions';

    const duplicate = document.createElement('button');
    duplicate.className = 'board-icon-btn';
    duplicate.type = 'button';
    duplicate.title = 'Duplicate sticky';
    duplicate.textContent = '⧉';
    duplicate.addEventListener('click', (event) => {
      event.stopPropagation();
      duplicateBoardItem(item.id);
    });

    const remove = document.createElement('button');
    remove.className = 'board-icon-btn danger';
    remove.type = 'button';
    remove.title = 'Delete sticky';
    remove.textContent = '×';
    remove.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteBoardItem(item.id);
    });

    actions.append(duplicate, remove);
    header.append(title, actions);

    const body = document.createElement('textarea');
    body.className = 'board-card-body-input';
    body.placeholder = 'Write the idea, task, shot note, or reference here…';
    body.value = item.content || '';
    body.addEventListener('input', () => {
      item.content = body.value;
      queueSave('Editing sticky…');
    });

    const palette = document.createElement('div');
    palette.className = 'board-card-palette';
    CARD_COLORS.forEach((color) => {
      const swatch = document.createElement('button');
      swatch.className = `board-color-dot board-color-${color}`;
      swatch.type = 'button';
      swatch.title = `Set ${color}`;
      swatch.setAttribute('aria-label', `Set sticky color ${color}`);
      swatch.dataset.active = normalizeCardColor(item.color) === color ? '1' : '0';
      swatch.addEventListener('click', (event) => {
        event.stopPropagation();
        item.color = color;
        applyCardColorStyle(card, item.color);
        updatePaletteActiveState(palette, item.color);
        queueSave('Color updated…');
      });
      palette.appendChild(swatch);
    });



    const customColor = document.createElement('input');
    customColor.className = 'board-color-dot board-color-custom';
    customColor.type = 'color';
    customColor.title = 'Choose custom color';
    customColor.setAttribute('aria-label', 'Choose custom sticky color');
    customColor.value = isHexColor(item.color) ? item.color : '#facc15';
    customColor.dataset.active = isCustomCardColor(item.color) ? '1' : '0';
    customColor.addEventListener('input', (event) => {
      event.stopPropagation();
      item.color = customColor.value;
      applyCardColorStyle(card, item.color);
      updatePaletteActiveState(palette, item.color);
      queueSave('Custom color updated…');
    });
    customColor.addEventListener('click', (event) => event.stopPropagation());
    palette.appendChild(customColor);

    const footer = document.createElement('div');
    footer.className = 'board-card-footer';
    footer.textContent = 'Drag from the top bar · Resize from corner';

    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'board-card-resize-handle';
    resizeHandle.title = 'Resize card';
    resizeHandle.setAttribute('aria-hidden', 'true');
    resizeHandle.addEventListener('pointerdown', (event) => handleResizePointerDown(event, item));

    card.addEventListener('pointerdown', (event) => handleCardPointerDown(event, item));

    card.append(header, body, palette, footer, resizeHandle);
    return card;
  }

  function buildTextLayer(item) {
    const card = document.createElement('article');
    card.className = 'board-card board-text-layer';
    card.dataset.itemId = item.id;
    card.dataset.selected = state.selectedItemId === item.id ? '1' : '0';
    card.style.left = `${Number(item.x || 150)}px`;
    card.style.top = `${Number(item.y || 150)}px`;
    card.style.width = `${Number(item.w || 260)}px`;
    card.style.height = `${Number(item.h || 90)}px`;
    card.style.zIndex = String(Number(item.z || 1));
    card.style.setProperty('--board-text-color', isHexColor(item.color) ? item.color : '#e2e8f0');

    const toolbar = document.createElement('div');
    toolbar.className = 'board-text-toolbar board-card-drag-handle';
    toolbar.title = 'Drag text layer';

    const dragLabel = document.createElement('span');
    dragLabel.className = 'board-text-drag-label';
    dragLabel.textContent = 'Move text';

    const color = document.createElement('input');
    color.className = 'board-text-color-input';
    color.type = 'color';
    color.title = 'Text color';
    color.value = isHexColor(item.color) ? item.color : '#e2e8f0';
    color.addEventListener('input', (event) => {
      event.stopPropagation();
      item.color = color.value;
      card.style.setProperty('--board-text-color', item.color);
      queueSave('Text color updated…');
    });
    color.addEventListener('click', (event) => event.stopPropagation());

    const duplicate = document.createElement('button');
    duplicate.className = 'board-icon-btn';
    duplicate.type = 'button';
    duplicate.title = 'Duplicate text layer';
    duplicate.textContent = '⧉';
    duplicate.addEventListener('click', (event) => {
      event.stopPropagation();
      duplicateBoardItem(item.id);
    });

    const remove = document.createElement('button');
    remove.className = 'board-icon-btn danger';
    remove.type = 'button';
    remove.title = 'Delete text layer';
    remove.textContent = '×';
    remove.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteBoardItem(item.id);
    });

    toolbar.append(dragLabel, color, duplicate, remove);

    const text = document.createElement('textarea');
    text.className = 'board-free-text-input';
    text.placeholder = 'Text';
    text.value = item.content || item.title || 'Text';
    text.addEventListener('input', () => {
      item.content = text.value;
      item.title = text.value.split('\n').find(Boolean)?.slice(0, 80) || 'Text';
      queueSave('Editing text…');
    });

    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'board-card-resize-handle board-text-resize-handle';
    resizeHandle.title = 'Resize text layer';
    resizeHandle.setAttribute('aria-hidden', 'true');
    resizeHandle.addEventListener('pointerdown', (event) => handleResizePointerDown(event, item));

    card.addEventListener('pointerdown', (event) => handleCardPointerDown(event, item));
    card.append(toolbar, text, resizeHandle);
    return card;
  }


  function buildImageCard(item) {
    const card = document.createElement('article');
    card.className = 'board-card board-image-card';
    card.dataset.itemId = item.id;
    card.dataset.selected = state.selectedItemId === item.id ? '1' : '0';
    card.style.left = `${Number(item.x || 120)}px`;
    card.style.top = `${Number(item.y || 120)}px`;
    card.style.width = `${Number(item.w || 320)}px`;
    card.style.height = `${Number(item.h || 260)}px`;
    card.style.zIndex = String(Number(item.z || 1));

    const header = document.createElement('div');
    header.className = 'board-image-header board-card-drag-handle';
    header.title = 'Drag image card';

    const title = document.createElement('input');
    title.className = 'board-image-title-input';
    title.type = 'text';
    title.maxLength = 120;
    title.value = item.title || 'Image reference';
    title.placeholder = 'Image title';
    title.addEventListener('input', () => {
      item.title = title.value;
      queueSave('Editing image title…');
    });

    const actions = document.createElement('div');
    actions.className = 'board-card-actions';

    const duplicate = document.createElement('button');
    duplicate.className = 'board-icon-btn';
    duplicate.type = 'button';
    duplicate.title = 'Duplicate image card';
    duplicate.textContent = '⧉';
    duplicate.addEventListener('click', (event) => {
      event.stopPropagation();
      duplicateBoardItem(item.id);
    });

    const remove = document.createElement('button');
    remove.className = 'board-icon-btn danger';
    remove.type = 'button';
    remove.title = 'Delete image card';
    remove.textContent = '×';
    remove.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteBoardItem(item.id);
    });

    actions.append(duplicate, remove);
    header.append(title, actions);

    const mediaWrap = document.createElement('div');
    mediaWrap.className = 'board-image-preview-wrap';
    const image = document.createElement('img');
    image.className = 'board-image-preview';
    image.alt = item.title || 'Board image reference';
    image.draggable = false;
    image.src = boardMediaUrl(item.media_path);
    mediaWrap.appendChild(image);

    const caption = document.createElement('textarea');
    caption.className = 'board-image-caption-input';
    caption.placeholder = 'Optional caption or reference note…';
    caption.value = item.content || '';
    caption.addEventListener('input', () => {
      item.content = caption.value;
      queueSave('Editing image caption…');
    });

    const footer = document.createElement('div');
    footer.className = 'board-card-footer board-image-footer';
    footer.textContent = 'Image card · Drag from top · Resize from corner';

    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'board-card-resize-handle board-image-resize-handle';
    resizeHandle.title = 'Resize image card';
    resizeHandle.setAttribute('aria-hidden', 'true');
    resizeHandle.addEventListener('pointerdown', (event) => handleResizePointerDown(event, item));

    card.addEventListener('pointerdown', (event) => handleCardPointerDown(event, item));
    card.append(header, mediaWrap, caption, footer, resizeHandle);
    return card;
  }

  function buildAudioCard(item) {
    const card = document.createElement('article');
    card.className = 'board-card board-audio-card';
    card.dataset.itemId = item.id;
    card.dataset.selected = state.selectedItemId === item.id ? '1' : '0';
    card.style.left = `${Number(item.x || 140)}px`;
    card.style.top = `${Number(item.y || 140)}px`;
    card.style.width = `${Number(item.w || 320)}px`;
    card.style.height = `${Number(item.h || 220)}px`;
    card.style.zIndex = String(Number(item.z || 1));

    const header = document.createElement('div');
    header.className = 'board-audio-header board-card-drag-handle';
    header.title = 'Drag audio card';

    const title = document.createElement('input');
    title.className = 'board-audio-title-input';
    title.type = 'text';
    title.maxLength = 120;
    title.value = item.title || 'Audio reference';
    title.placeholder = 'Audio title';
    title.addEventListener('input', () => {
      item.title = title.value;
      queueSave('Editing audio title…');
    });

    const actions = document.createElement('div');
    actions.className = 'board-card-actions';

    const duplicate = document.createElement('button');
    duplicate.className = 'board-icon-btn';
    duplicate.type = 'button';
    duplicate.title = 'Duplicate audio card';
    duplicate.textContent = '⧉';
    duplicate.addEventListener('click', (event) => {
      event.stopPropagation();
      duplicateBoardItem(item.id);
    });

    const remove = document.createElement('button');
    remove.className = 'board-icon-btn danger';
    remove.type = 'button';
    remove.title = 'Delete audio card';
    remove.textContent = '×';
    remove.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteBoardItem(item.id);
    });

    actions.append(duplicate, remove);
    header.append(title, actions);

    const mediaWrap = document.createElement('div');
    mediaWrap.className = 'board-audio-player-wrap';

    const icon = document.createElement('div');
    icon.className = 'board-audio-icon';
    icon.textContent = '♫';
    icon.setAttribute('aria-hidden', 'true');

    const player = document.createElement('audio');
    player.className = 'board-audio-player';
    player.controls = true;
    player.preload = 'metadata';
    player.src = boardMediaUrl(item.media_path);
    player.addEventListener('pointerdown', (event) => event.stopPropagation());

    mediaWrap.append(icon, player);

    const caption = document.createElement('textarea');
    caption.className = 'board-audio-caption-input';
    caption.placeholder = 'Optional caption, transcript hint, or reference note…';
    caption.value = item.content || '';
    caption.addEventListener('input', () => {
      item.content = caption.value;
      queueSave('Editing audio caption…');
    });

    const footer = document.createElement('div');
    footer.className = 'board-card-footer board-audio-footer';
    footer.textContent = 'Audio card · Drag from top · Resize from corner';

    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'board-card-resize-handle board-audio-resize-handle';
    resizeHandle.title = 'Resize audio card';
    resizeHandle.setAttribute('aria-hidden', 'true');
    resizeHandle.addEventListener('pointerdown', (event) => handleResizePointerDown(event, item));

    card.addEventListener('pointerdown', (event) => handleCardPointerDown(event, item));
    card.append(header, mediaWrap, caption, footer, resizeHandle);
    return card;
  }

  function buildVideoCard(item) {
    const card = document.createElement('article');
    card.className = 'board-card board-video-card';
    card.dataset.itemId = item.id;
    card.dataset.selected = state.selectedItemId === item.id ? '1' : '0';
    card.style.left = `${Number(item.x || 150)}px`;
    card.style.top = `${Number(item.y || 150)}px`;
    card.style.width = `${Number(item.w || 380)}px`;
    card.style.height = `${Number(item.h || 300)}px`;
    card.style.zIndex = String(Number(item.z || 1));

    const header = document.createElement('div');
    header.className = 'board-video-header board-card-drag-handle';
    header.title = 'Drag video card';

    const title = document.createElement('input');
    title.className = 'board-video-title-input';
    title.type = 'text';
    title.maxLength = 120;
    title.value = item.title || 'Video reference';
    title.placeholder = 'Video title';
    title.addEventListener('input', () => {
      item.title = title.value;
      queueSave('Editing video title…');
    });

    const actions = document.createElement('div');
    actions.className = 'board-card-actions';

    const duplicate = document.createElement('button');
    duplicate.className = 'board-icon-btn';
    duplicate.type = 'button';
    duplicate.title = 'Duplicate video card';
    duplicate.textContent = '⧉';
    duplicate.addEventListener('click', (event) => {
      event.stopPropagation();
      duplicateBoardItem(item.id);
    });

    const remove = document.createElement('button');
    remove.className = 'board-icon-btn danger';
    remove.type = 'button';
    remove.title = 'Delete video card';
    remove.textContent = '×';
    remove.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteBoardItem(item.id);
    });

    actions.append(duplicate, remove);
    header.append(title, actions);

    const mediaWrap = document.createElement('div');
    mediaWrap.className = 'board-video-preview-wrap';
    const video = document.createElement('video');
    video.className = 'board-video-preview';
    video.controls = true;
    video.preload = 'metadata';
    video.src = boardMediaUrl(item.media_path);
    video.addEventListener('pointerdown', (event) => event.stopPropagation());
    mediaWrap.appendChild(video);

    const caption = document.createElement('textarea');
    caption.className = 'board-video-caption-input';
    caption.placeholder = 'Optional caption, shot note, or reference context…';
    caption.value = item.content || '';
    caption.addEventListener('input', () => {
      item.content = caption.value;
      queueSave('Editing video caption…');
    });

    const footer = document.createElement('div');
    footer.className = 'board-card-footer board-video-footer';
    footer.textContent = 'Video card · Drag from top · Resize from corner';

    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'board-card-resize-handle board-video-resize-handle';
    resizeHandle.title = 'Resize video card';
    resizeHandle.setAttribute('aria-hidden', 'true');
    resizeHandle.addEventListener('pointerdown', (event) => handleResizePointerDown(event, item));

    card.addEventListener('pointerdown', (event) => handleCardPointerDown(event, item));
    card.append(header, mediaWrap, caption, footer, resizeHandle);
    return card;
  }

  function boardMediaUrl(mediaPath) {
    const clean = String(mediaPath || '').replace(/^\/+/, '');
    if (!clean) return '';
    return `/api/board/media/${clean.split('/').map(encodeURIComponent).join('/')}`;
  }

  function buildChecklistCard(item) {
    if (!Array.isArray(item.checked_items)) item.checked_items = [];
    const card = document.createElement('article');
    card.className = `board-card board-checklist board-card-${normalizeCardColor(item.color || 'mint')}`;
    applyCardColorStyle(card, item.color || 'mint');
    card.dataset.itemId = item.id;
    card.dataset.selected = state.selectedItemId === item.id ? '1' : '0';
    card.style.left = `${Number(item.x || 140)}px`;
    card.style.top = `${Number(item.y || 140)}px`;
    card.style.width = `${Number(item.w || 320)}px`;
    card.style.height = `${Number(item.h || 250)}px`;
    card.style.zIndex = String(Number(item.z || 1));

    const header = document.createElement('div');
    header.className = 'board-card-header board-card-drag-handle';
    header.title = 'Drag to move';

    const title = document.createElement('input');
    title.className = 'board-card-title-input';
    title.type = 'text';
    title.maxLength = 120;
    title.value = item.title || 'Checklist';
    title.placeholder = 'Checklist title';
    title.addEventListener('input', () => {
      item.title = title.value;
      queueSave('Editing checklist…');
    });

    const actions = document.createElement('div');
    actions.className = 'board-card-actions';

    const duplicate = document.createElement('button');
    duplicate.className = 'board-icon-btn';
    duplicate.type = 'button';
    duplicate.title = 'Duplicate checklist';
    duplicate.textContent = '⧉';
    duplicate.addEventListener('click', (event) => {
      event.stopPropagation();
      duplicateBoardItem(item.id);
    });

    const remove = document.createElement('button');
    remove.className = 'board-icon-btn danger';
    remove.type = 'button';
    remove.title = 'Delete checklist';
    remove.textContent = '×';
    remove.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteBoardItem(item.id);
    });

    actions.append(duplicate, remove);
    header.append(title, actions);

    const list = document.createElement('div');
    list.className = 'board-checklist-items';
    if (!item.checked_items.length) item.checked_items.push(buildChecklistItem('New task'));
    item.checked_items.forEach((task) => list.appendChild(buildChecklistRow(item, task)));

    const addTask = document.createElement('button');
    addTask.className = 'board-checklist-add';
    addTask.type = 'button';
    addTask.textContent = '+ Add task';
    addTask.addEventListener('click', (event) => {
      event.stopPropagation();
      item.checked_items.push(buildChecklistItem(''));
      queueSave('Adding checklist item…', 0);
      renderCurrentBoard();
      setTimeout(() => {
        const rows = document.querySelectorAll(`[data-item-id="${item.id}"] .board-checklist-text`);
        const last = rows[rows.length - 1];
        if (last) last.focus();
      }, 0);
    });

    const palette = document.createElement('div');
    palette.className = 'board-card-palette';
    CARD_COLORS.forEach((color) => {
      const swatch = document.createElement('button');
      swatch.className = `board-color-dot board-color-${color}`;
      swatch.type = 'button';
      swatch.title = `Set ${color}`;
      swatch.setAttribute('aria-label', `Set checklist color ${color}`);
      swatch.dataset.active = normalizeCardColor(item.color || 'mint') === color ? '1' : '0';
      swatch.addEventListener('click', (event) => {
        event.stopPropagation();
        item.color = color;
        applyCardColorStyle(card, item.color);
        updatePaletteActiveState(palette, item.color);
        queueSave('Checklist color updated…');
      });
      palette.appendChild(swatch);
    });

    const customColor = document.createElement('input');
    customColor.className = 'board-color-dot board-color-custom';
    customColor.type = 'color';
    customColor.title = 'Choose custom color';
    customColor.setAttribute('aria-label', 'Choose custom checklist color');
    customColor.value = isHexColor(item.color) ? item.color : '#4ade80';
    customColor.dataset.active = isCustomCardColor(item.color) ? '1' : '0';
    customColor.addEventListener('input', (event) => {
      event.stopPropagation();
      item.color = customColor.value;
      applyCardColorStyle(card, item.color);
      updatePaletteActiveState(palette, item.color);
      queueSave('Custom checklist color updated…');
    });
    customColor.addEventListener('click', (event) => event.stopPropagation());
    palette.appendChild(customColor);

    const footer = document.createElement('div');
    footer.className = 'board-card-footer';
    footer.textContent = 'Checklist · Drag from top · Resize from corner';

    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'board-card-resize-handle';
    resizeHandle.title = 'Resize card';
    resizeHandle.setAttribute('aria-hidden', 'true');
    resizeHandle.addEventListener('pointerdown', (event) => handleResizePointerDown(event, item));

    card.addEventListener('pointerdown', (event) => handleCardPointerDown(event, item));
    card.append(header, list, addTask, palette, footer, resizeHandle);
    return card;
  }

  function buildChecklistRow(cardItem, task) {
    normalizeChecklistTaskShape(task, cardItem.color);
    const row = document.createElement('div');
    row.className = 'board-checklist-row-wrap';
    row.dataset.checked = task.checked ? '1' : '0';

    const main = document.createElement('label');
    main.className = 'board-checklist-row';
    main.dataset.checked = task.checked ? '1' : '0';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = !!task.checked;
    checkbox.addEventListener('change', () => {
      task.checked = checkbox.checked;
      row.dataset.checked = task.checked ? '1' : '0';
      main.dataset.checked = task.checked ? '1' : '0';
      applyChecklistTaskColorToLinkedCards(task);
      updateLinkedCardsForChecklistTask(task);
      queueSave('Checklist links updated…');
      renderCurrentBoard();
    });

    const taskColor = document.createElement('input');
    taskColor.className = 'board-checklist-task-color';
    taskColor.type = 'color';
    taskColor.title = 'Task color for linked cards';
    taskColor.setAttribute('aria-label', 'Checklist task color');
    taskColor.value = normalizeChecklistTaskColor(task.color, cardItem.color);
    task.color = taskColor.value;
    taskColor.addEventListener('input', (event) => {
      event.preventDefault();
      event.stopPropagation();
      task.color = taskColor.value;
      applyChecklistTaskColorToLinkedCards(task);
      queueSave('Task color updated…', 0);
      renderCurrentBoard();
    });
    taskColor.addEventListener('click', (event) => event.stopPropagation());

    const text = document.createElement('input');
    text.className = 'board-checklist-text';
    text.type = 'text';
    text.maxLength = 500;
    text.value = task.text || '';
    text.placeholder = 'Checklist item';
    text.addEventListener('input', () => {
      task.text = text.value;
      queueSave('Editing checklist item…');
    });

    const link = document.createElement('button');
    link.className = 'board-checklist-link';
    link.type = 'button';
    link.title = 'Link cards to this task';
    link.textContent = (task.linked_item_ids || []).length ? `🔗 ${(task.linked_item_ids || []).length}` : '🔗';
    link.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const panel = row.querySelector('.board-checklist-link-panel');
      if (panel) panel.hidden = !panel.hidden;
    });

    const remove = document.createElement('button');
    remove.className = 'board-checklist-remove';
    remove.type = 'button';
    remove.title = 'Remove checklist item';
    remove.textContent = '×';
    remove.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      cardItem.checked_items = (cardItem.checked_items || []).filter((candidate) => candidate.id !== task.id);
      if (!cardItem.checked_items.length) cardItem.checked_items.push(buildChecklistItem(''));
      queueSave('Removing checklist item…', 0);
      renderCurrentBoard();
    });

    main.append(taskColor, checkbox, text, link, remove);
    row.append(main, buildChecklistLinkPanel(cardItem, task));
    return row;
  }

  function buildChecklistLinkPanel(cardItem, task) {
    normalizeChecklistTaskShape(task);
    const panel = document.createElement('div');
    panel.className = 'board-checklist-link-panel';
    panel.hidden = true;

    const candidates = getLinkableBoardItems(cardItem.id);
    if (!candidates.length) {
      const empty = document.createElement('div');
      empty.className = 'board-checklist-link-empty';
      empty.textContent = 'No other cards to link yet.';
      panel.appendChild(empty);
      return panel;
    }

    const head = document.createElement('div');
    head.className = 'board-checklist-link-head';
    head.textContent = 'Linked cards';
    panel.appendChild(head);

    candidates.forEach((candidate) => {
      const line = document.createElement('label');
      line.className = 'board-checklist-link-option';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = (task.linked_item_ids || []).includes(candidate.id);
      checkbox.addEventListener('change', (event) => {
        event.stopPropagation();
        const links = new Set(task.linked_item_ids || []);
        if (checkbox.checked) links.add(candidate.id);
        else links.delete(candidate.id);
        task.linked_item_ids = Array.from(links);
        applyChecklistTaskColorToLinkedCards(task);
        updateLinkedCardsForChecklistTask(task);
        queueSave('Checklist card links updated…', 0);
        renderCurrentBoard();
      });

      const name = document.createElement('span');
      name.textContent = cardDisplayName(candidate);

      const type = document.createElement('small');
      type.textContent = candidate.type || 'card';

      line.append(checkbox, name, type);
      panel.appendChild(line);
    });

    return panel;
  }

  function buildChecklistItem(text) {
    return { id: makeClientId('check'), text: text || '', checked: false, color: '#4ade80', linked_item_ids: [] };
  }

  function normalizeChecklistTaskShape(task, fallbackColor) {
    if (!task || typeof task !== 'object') return;
    if (!Array.isArray(task.linked_item_ids)) task.linked_item_ids = [];
    task.linked_item_ids = task.linked_item_ids.map((id) => String(id || '').trim()).filter(Boolean);
    task.color = normalizeChecklistTaskColor(task.color, fallbackColor);
  }

  function normalizeChecklistTaskColor(color, fallbackColor) {
    const clean = String(color || '').trim();
    if (isHexColor(clean)) return clean;
    return cardColorToHex(fallbackColor || 'mint');
  }

  function cardColorToHex(color) {
    const clean = String(color || '').trim().toLowerCase();
    if (isHexColor(clean)) return clean;
    return CARD_COLOR_HEX[clean] || CARD_COLOR_HEX.mint;
  }

  function getLinkableBoardItems(checklistCardId) {
    const items = state.currentBoard?.items || [];
    return items.filter((candidate) => candidate && candidate.id !== checklistCardId && candidate.type !== 'checklist');
  }

  function cardDisplayName(item) {
    if (!item) return 'Card';
    const text = String(item.title || item.content || '').trim();
    if (text) return text.length > 42 ? `${text.slice(0, 39)}…` : text;
    if (item.type === 'text') return 'Text layer';
    if (item.type === 'image') return 'Image card';
    if (item.type === 'audio') return 'Audio card';
    if (item.type === 'video') return 'Video card';
    return 'Sticky note';
  }

  function getChecklistLinkStateForItem(itemId) {
    const tasks = [];
    (state.currentBoard?.items || []).forEach((card) => {
      if (!card || card.type !== 'checklist' || !Array.isArray(card.checked_items)) return;
      card.checked_items.forEach((task) => {
        normalizeChecklistTaskShape(task, card.color);
        if ((task.linked_item_ids || []).includes(itemId)) {
          tasks.push({ task, checklist: card });
        }
      });
    });
    const completed = tasks.filter((entry) => entry.task.checked);
    const colorEntry = tasks.find((entry) => isHexColor(entry.task.color));
    return {
      linked: tasks.length > 0,
      disabled: completed.length > 0,
      count: tasks.length,
      completedCount: completed.length,
      color: colorEntry ? colorEntry.task.color : '',
      label: completed.map((entry) => entry.task.text || entry.checklist.title || 'Completed task').filter(Boolean).join(', '),
    };
  }

  function applyChecklistLinkedState(card, item) {
    if (!card || !item || item.type === 'checklist') return;
    const linkState = getChecklistLinkStateForItem(item.id);
    card.classList.toggle('board-card-linked', linkState.linked);
    card.classList.toggle('board-card-linked-complete', linkState.disabled);
    card.classList.toggle('board-card-linked-colored', !!linkState.color);
    card.dataset.linkedComplete = linkState.disabled ? '1' : '0';
    if (linkState.color) card.style.setProperty('--board-linked-color', linkState.color);
    else card.style.removeProperty('--board-linked-color');
    card.title = linkState.disabled ? `Linked to completed checklist task: ${linkState.label || 'completed'}` : (card.title || '');
    if (linkState.disabled && !card.querySelector('.board-linked-complete-badge')) {
      const badge = document.createElement('div');
      badge.className = 'board-linked-complete-badge';
      badge.textContent = 'Done link';
      card.appendChild(badge);
    }
  }

  function applyChecklistTaskColorToLinkedCards(task) {
    normalizeChecklistTaskShape(task);
    const color = normalizeChecklistTaskColor(task.color, 'mint');
    task.color = color;
    (task.linked_item_ids || []).forEach((itemId) => {
      const item = findBoardItem(itemId);
      if (!item || item.type === 'checklist') return;
      item.color = color;
      const card = document.querySelector(`.board-card[data-item-id="${CSS.escape(itemId)}"]`);
      if (!card) return;
      if (item.type === 'text') {
        card.style.setProperty('--board-text-color', color);
      } else if (item.type === 'sticky') {
        applyCardColorStyle(card, color);
      }
      card.style.setProperty('--board-linked-color', color);
      card.classList.add('board-card-linked-colored');
    });
  }

  function refreshLinkedCardColorInheritance() {
    (state.currentBoard?.items || []).forEach((card) => {
      if (!card || card.type !== 'checklist' || !Array.isArray(card.checked_items)) return;
      card.checked_items.forEach((task) => applyChecklistTaskColorToLinkedCards(task));
    });
  }

  function updateLinkedCardsForChecklistTask(task) {
    normalizeChecklistTaskShape(task);
    (task.linked_item_ids || []).forEach((itemId) => {
      const card = document.querySelector(`.board-card[data-item-id="${CSS.escape(itemId)}"]`);
      const item = findBoardItem(itemId);
      if (card && item) applyChecklistLinkedState(card, item);
    });
  }

  function pruneChecklistLinksForDeletedItem(deletedItemId) {
    let changed = false;
    (state.currentBoard?.items || []).forEach((card) => {
      if (!card || card.type !== 'checklist' || !Array.isArray(card.checked_items)) return;
      card.checked_items.forEach((task) => {
        normalizeChecklistTaskShape(task);
        const before = task.linked_item_ids.length;
        task.linked_item_ids = task.linked_item_ids.filter((id) => id !== deletedItemId);
        if (task.linked_item_ids.length !== before) changed = true;
      });
    });
    return changed;
  }

  function isInteractiveTarget(target) {
    return !!(target && target.closest && target.closest('input, textarea, button, select, option, [contenteditable="true"]'));
  }

  function findBoardItem(itemId) {
    if (!state.currentBoard || !Array.isArray(state.currentBoard.items)) return null;
    return state.currentBoard.items.find((item) => item && item.id === itemId) || null;
  }

  function maxBoardZ() {
    const items = state.currentBoard?.items || [];
    return Math.max(0, ...items.map((item) => Number(item.z || 0)));
  }

  function selectBoardItem(itemId, options) {
    const item = findBoardItem(itemId);
    if (!item) return false;
    state.selectedItemId = item.id;
    let changed = false;
    if (!options || options.bringToFront !== false) {
      const currentMax = maxBoardZ();
      if (Number(item.z || 0) < currentMax) {
        item.z = currentMax + 1;
        changed = true;
      }
    }
    document.querySelectorAll('.board-card[data-selected="1"]').forEach((node) => {
      if (node.dataset.itemId !== item.id) node.dataset.selected = '0';
    });
    const node = document.querySelector(`.board-card[data-item-id="${CSS.escape(item.id)}"]`);
    if (node) {
      node.dataset.selected = '1';
      node.style.zIndex = String(Number(item.z || 1));
    }
    return changed;
  }

  function readRenderedCardPosition(card, item) {
    const renderedX = Number.isFinite(card?.offsetLeft) ? card.offsetLeft : Number(item?.x || 0);
    const renderedY = Number.isFinite(card?.offsetTop) ? card.offsetTop : Number(item?.y || 0);
    return {
      x: Math.max(0, Math.round(renderedX)),
      y: Math.max(0, Math.round(renderedY)),
    };
  }

  function syncRenderedCardPositions() {
    if (!state.currentBoard || !Array.isArray(state.currentBoard.items)) return;
    document.querySelectorAll('#board-canvas .board-card[data-item-id]').forEach((card) => {
      const item = findBoardItem(card.dataset.itemId);
      if (!item) return;
      const pos = readRenderedCardPosition(card, item);
      item.x = pos.x;
      item.y = pos.y;
    });
  }

  function getCardMinSize(item) {
    if (item?.type === 'text') return { w: 80, h: 40 };
    if (item?.type === 'image') return { w: 180, h: 160 };
    if (item?.type === 'audio') return { w: 240, h: 180 };
    if (item?.type === 'video') return { w: 280, h: 220 };
    return { w: 220, h: 160 };
  }

  function readRenderedCardSize(card, item) {
    const minimum = getCardMinSize(item);
    const renderedW = Number.isFinite(card?.offsetWidth) ? card.offsetWidth : Number(item?.w || 280);
    const renderedH = Number.isFinite(card?.offsetHeight) ? card.offsetHeight : Number(item?.h || 190);
    return {
      w: Math.max(minimum.w, Math.round(renderedW)),
      h: Math.max(minimum.h, Math.round(renderedH)),
    };
  }

  function syncRenderedCardSizes() {
    if (!state.currentBoard || !Array.isArray(state.currentBoard.items)) return;
    document.querySelectorAll('#board-canvas .board-card[data-item-id]').forEach((card) => {
      const item = findBoardItem(card.dataset.itemId);
      if (!item) return;
      const size = readRenderedCardSize(card, item);
      item.w = size.w;
      item.h = size.h;
    });
  }

  function handleResizePointerDown(event, item) {
    if (!item || event.button !== 0) return;
    const card = event.currentTarget.closest('.board-card');
    if (!card) return;
    const renderedSize = readRenderedCardSize(card, item);
    const renderedPos = readRenderedCardPosition(card, item);
    item.x = renderedPos.x;
    item.y = renderedPos.y;
    item.w = renderedSize.w;
    item.h = renderedSize.h;
    const zChanged = selectBoardItem(item.id, { bringToFront: true });
    state.resize = {
      itemId: item.id,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startW: renderedSize.w,
      startH: renderedSize.h,
      changed: false,
      zChanged,
    };
    card.classList.add('is-resizing');
    try { card.setPointerCapture(event.pointerId); } catch (_) {}
    event.preventDefault();
    event.stopPropagation();
  }

  function shouldStartCanvasPan(event) {
    if (!state.currentBoard) return false;
    if (event.button === 1) return true;
    if (state.spacePanning && event.button === 0) return true;
    return event.button === 0 && event.target && event.target.id === 'board-canvas';
  }

  function handleCanvasPointerDown(event) {
    if (!shouldStartCanvasPan(event)) return;
    const view = getCanvasView();
    state.pan = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startPanX: view.pan_x,
      startPanY: view.pan_y,
      moved: false,
    };
    renderCanvasView();
    try { event.currentTarget.setPointerCapture(event.pointerId); } catch (_) {}
    event.preventDefault();
  }

  function handleDocumentPanMove(event, pan) {
    if (!state.currentBoard) return;
    const view = getCanvasView();
    const nextX = Math.round(pan.startPanX + event.clientX - pan.startClientX);
    const nextY = Math.round(pan.startPanY + event.clientY - pan.startClientY);
    if (Math.abs(nextX - pan.startPanX) > 1 || Math.abs(nextY - pan.startPanY) > 1) pan.moved = true;
    view.pan_x = nextX;
    view.pan_y = nextY;
    renderCanvasView();
  }

  function finishCanvasPan(event) {
    const pan = state.pan;
    if (!pan || pan.pointerId !== event.pointerId) return false;
    const canvas = $('board-canvas');
    if (canvas) {
      try { canvas.releasePointerCapture(event.pointerId); } catch (_) {}
    }
    state.pan = null;
    renderCanvasView();
    if (pan.moved) queueSave('View position updated…', 700);
    return true;
  }

  function handleCardPointerDown(event, item) {
    if (!item || event.button !== 0 || isInteractiveTarget(event.target) || event.target.closest('.board-card-resize-handle')) return;
    const card = event.currentTarget;
    const renderedPos = readRenderedCardPosition(card, item);
    item.x = renderedPos.x;
    item.y = renderedPos.y;
    const zChanged = selectBoardItem(item.id, { bringToFront: true });
    const startX = renderedPos.x;
    const startY = renderedPos.y;
    state.drag = {
      itemId: item.id,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX,
      startY,
      moved: false,
      zChanged,
    };
    card.classList.add('is-dragging');
    try { card.setPointerCapture(event.pointerId); } catch (_) {}
    event.preventDefault();
  }

  function handleDocumentPointerMove(event) {
    const pan = state.pan;
    if (pan && pan.pointerId === event.pointerId) {
      handleDocumentPanMove(event, pan);
      return;
    }
    const resize = state.resize;
    if (resize && resize.pointerId === event.pointerId) {
      handleDocumentResizeMove(event, resize);
      return;
    }
    const drag = state.drag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const item = findBoardItem(drag.itemId);
    const card = document.querySelector(`.board-card[data-item-id="${CSS.escape(drag.itemId)}"]`);
    if (!item || !card) return;
    const zoom = getCanvasZoom();
    const nextX = Math.max(0, Math.round(drag.startX + (event.clientX - drag.startClientX) / zoom));
    const nextY = Math.max(0, Math.round(drag.startY + (event.clientY - drag.startClientY) / zoom));
    if (Math.abs(nextX - drag.startX) > 1 || Math.abs(nextY - drag.startY) > 1) drag.moved = true;
    item.x = nextX;
    item.y = nextY;
    card.style.left = `${nextX}px`;
    card.style.top = `${nextY}px`;
    const canvas = $('board-canvas');
    if (canvas) applyCanvasBounds(canvas, state.currentBoard?.items || []);
  }

  function handleDocumentResizeMove(event, resize) {
    const item = findBoardItem(resize.itemId);
    const card = document.querySelector(`.board-card[data-item-id="${CSS.escape(resize.itemId)}"]`);
    if (!item || !card) return;
    const minimum = getCardMinSize(item);
    const zoom = getCanvasZoom();
    const nextW = Math.max(minimum.w, Math.round(resize.startW + (event.clientX - resize.startClientX) / zoom));
    const nextH = Math.max(minimum.h, Math.round(resize.startH + (event.clientY - resize.startClientY) / zoom));
    if (Math.abs(nextW - resize.startW) > 1 || Math.abs(nextH - resize.startH) > 1) resize.changed = true;
    item.w = nextW;
    item.h = nextH;
    card.style.width = `${nextW}px`;
    card.style.height = `${nextH}px`;
    const canvas = $('board-canvas');
    if (canvas) applyCanvasBounds(canvas, state.currentBoard?.items || []);
  }

  function handleDocumentPointerUp(event) {
    if (finishCanvasPan(event)) return;
    const resize = state.resize;
    if (resize && resize.pointerId === event.pointerId) {
      const card = document.querySelector(`.board-card[data-item-id="${CSS.escape(resize.itemId)}"]`);
      if (card) {
        card.classList.remove('is-resizing');
        try { card.releasePointerCapture(event.pointerId); } catch (_) {}
      }
      const item = findBoardItem(resize.itemId);
      if (item && (resize.changed || resize.zChanged)) {
        queueSave(resize.changed ? 'Size updated…' : 'Layer updated…', 120);
      }
      state.resize = null;
      return;
    }
    const drag = state.drag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const card = document.querySelector(`.board-card[data-item-id="${CSS.escape(drag.itemId)}"]`);
    if (card) {
      card.classList.remove('is-dragging');
      try { card.releasePointerCapture(event.pointerId); } catch (_) {}
    }
    const item = findBoardItem(drag.itemId);
    if (item && (drag.moved || drag.zChanged)) {
      queueSave(drag.moved ? 'Position updated…' : 'Layer updated…', 120);
    }
    state.drag = null;
  }

  function normalizeCardColor(color) {
    const clean = String(color || '').trim().toLowerCase();
    return CARD_COLORS.includes(clean) ? clean : 'custom';
  }

  function isHexColor(color) {
    return /^#[0-9a-f]{6}$/i.test(String(color || '').trim());
  }

  function isCustomCardColor(color) {
    const clean = String(color || '').trim().toLowerCase();
    return isHexColor(clean) && !CARD_COLORS.includes(clean);
  }

  function applyCardColorStyle(card, color) {
    if (!card) return;
    const preset = CARD_COLORS.includes(String(color || '').trim().toLowerCase()) ? String(color).trim().toLowerCase() : '';
    CARD_COLORS.forEach((name) => card.classList.toggle(`board-card-${name}`, preset === name));
    card.classList.toggle('board-card-custom', !preset);
    if (!preset && isHexColor(color)) {
      card.style.setProperty('--board-card-custom-color', color);
    } else {
      card.style.removeProperty('--board-card-custom-color');
    }
  }

  function updatePaletteActiveState(palette, color) {
    if (!palette) return;
    const clean = String(color || '').trim().toLowerCase();
    palette.querySelectorAll('.board-color-dot').forEach((dot) => {
      const dotPreset = Array.from(dot.classList).find((name) => name.startsWith('board-color-') && name !== 'board-color-dot' && name !== 'board-color-custom');
      const presetName = dotPreset ? dotPreset.replace('board-color-', '') : '';
      const active = presetName ? clean === presetName : isCustomCardColor(clean);
      dot.dataset.active = active ? '1' : '0';
      if (dot.type === 'color' && isHexColor(clean)) dot.value = clean;
    });
  }

  function nextCardPosition() {
    const items = state.currentBoard?.items || [];
    const count = items.length;
    return {
      x: 96 + ((count * 34) % 360),
      y: 96 + ((count * 28) % 260),
      z: Math.max(0, ...items.map((item) => Number(item.z || 0))) + 1,
    };
  }

  function createStickyNote() {
    if (!state.currentBoard) return;
    const pos = nextCardPosition();
    const item = {
      id: makeClientId('item'),
      type: 'sticky',
      x: pos.x,
      y: pos.y,
      w: 280,
      h: 190,
      z: pos.z,
      color: 'gold',
      title: 'New sticky',
      content: '',
      checked_items: [],
      media_path: '',
      media_kind: '',
    };
    state.currentBoard.items.push(item);
    state.selectedItemId = item.id;
    queueSave('Adding sticky…', 0);
    renderCurrentBoard();
    setTimeout(() => {
      const input = document.querySelector(`[data-item-id="${item.id}"] .board-card-title-input`);
      if (input) input.focus();
    }, 0);
  }

  function createChecklistCard() {
    if (!state.currentBoard) return;
    const pos = nextCardPosition();
    const item = {
      id: makeClientId('item'),
      type: 'checklist',
      x: pos.x,
      y: pos.y,
      w: 320,
      h: 250,
      z: pos.z,
      color: 'mint',
      title: 'New checklist',
      content: '',
      checked_items: [buildChecklistItem('First task')],
      media_path: '',
      media_kind: '',
    };
    state.currentBoard.items.push(item);
    state.selectedItemId = item.id;
    queueSave('Adding checklist…', 0);
    renderCurrentBoard();
    setTimeout(() => {
      const input = document.querySelector(`[data-item-id="${item.id}"] .board-card-title-input`);
      if (input) input.focus();
    }, 0);
  }

  function createTextNote() {
    if (!state.currentBoard) return;
    const pos = nextCardPosition();
    const item = {
      id: makeClientId('item'),
      type: 'text',
      x: pos.x,
      y: pos.y,
      w: 260,
      h: 90,
      z: pos.z,
      color: '#e2e8f0',
      title: 'Text',
      content: '',
      checked_items: [],
      media_path: '',
      media_kind: '',
    };
    state.currentBoard.items.push(item);
    state.selectedItemId = item.id;
    queueSave('Adding text…', 0);
    renderCurrentBoard();
    setTimeout(() => {
      const input = document.querySelector(`[data-item-id="${item.id}"] .board-free-text-input`);
      if (input) input.focus();
    }, 0);
  }


  async function createImageCardFromFile(file) {
    if (!state.currentBoard || !file) return;
    if (!String(file.type || '').startsWith('image/')) {
      setStatus('Choose a supported image file.');
      return;
    }
    setBadge('Uploading');
    setStatus('Uploading image…');
    const form = new FormData();
    form.append('file', file);
    try {
      const response = await fetch(IMAGE_MEDIA_ROOT, { method: 'POST', body: form });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.detail || 'Image upload failed.');
      const media = payload.media || {};
      const pos = nextCardPosition();
      const item = {
        id: makeClientId('item'),
        type: 'image',
        x: pos.x,
        y: pos.y,
        w: 340,
        h: 280,
        z: pos.z,
        color: '',
        title: media.filename || file.name || 'Image reference',
        content: '',
        checked_items: [],
        media_path: media.media_path || '',
        media_kind: 'image',
      };
      state.currentBoard.items.push(item);
      state.selectedItemId = item.id;
      queueSave('Adding image…', 0);
      renderCurrentBoard();
    } catch (error) {
      setBadge('Error');
      setStatus(error.message || 'Image upload failed');
    }
  }

  async function createAudioCardFromFile(file, options) {
    const audioOptions = options || {};
    if (!state.currentBoard || !file) return;
    const fileType = String(file.type || '').toLowerCase();
    const fileName = String(file.name || '').toLowerCase();
    const looksAudio = fileType.startsWith('audio/') || /\.(mp3|wav|ogg|m4a|aac|flac|webm)$/.test(fileName);
    if (!looksAudio) {
      setStatus('Choose a supported audio file.');
      return;
    }
    setBadge('Uploading');
    setStatus('Uploading audio…');
    const form = new FormData();
    form.append('file', file);
    try {
      const response = await fetch(AUDIO_MEDIA_ROOT, { method: 'POST', body: form });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.detail || 'Audio upload failed.');
      const media = payload.media || {};
      const pos = nextCardPosition();
      const item = {
        id: makeClientId('item'),
        type: 'audio',
        x: pos.x,
        y: pos.y,
        w: 340,
        h: 220,
        z: pos.z,
        color: '',
        title: audioOptions.title || media.filename || file.name || 'Audio reference',
        content: audioOptions.content || '',
        checked_items: [],
        media_path: media.media_path || '',
        media_kind: 'audio',
      };
      state.currentBoard.items.push(item);
      state.selectedItemId = item.id;
      queueSave('Adding audio…', 0);
      renderCurrentBoard();
    } catch (error) {
      setBadge('Error');
      setStatus(error.message || 'Audio upload failed');
    }
  }

  async function createVideoCardFromFile(file) {
    if (!state.currentBoard || !file) return;
    const fileType = String(file.type || '').toLowerCase();
    const fileName = String(file.name || '').toLowerCase();
    const looksVideo = fileType.startsWith('video/') || /\.(mp4|webm|mov|m4v|ogv)$/.test(fileName);
    if (!looksVideo) {
      setStatus('Choose a supported video file.');
      return;
    }
    setBadge('Uploading');
    setStatus('Uploading video…');
    const form = new FormData();
    form.append('file', file);
    try {
      const response = await fetch(VIDEO_MEDIA_ROOT, { method: 'POST', body: form });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.detail || 'Video upload failed.');
      const media = payload.media || {};
      const pos = nextCardPosition();
      const item = {
        id: makeClientId('item'),
        type: 'video',
        x: pos.x,
        y: pos.y,
        w: 420,
        h: 320,
        z: pos.z,
        color: '',
        title: media.filename || file.name || 'Video reference',
        content: '',
        checked_items: [],
        media_path: media.media_path || '',
        media_kind: 'video',
      };
      state.currentBoard.items.push(item);
      state.selectedItemId = item.id;
      queueSave('Adding video…', 0);
      renderCurrentBoard();
    } catch (error) {
      setBadge('Error');
      setStatus(error.message || 'Video upload failed');
    }
  }


  function supportsAudioRecording() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }

  function preferredRecorderMimeType() {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg'];
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || '';
  }

  function updateRecorderButton() {
    const button = $('board-record-audio');
    if (!button) return;
    const isRecording = !!state.recorder;
    button.textContent = isRecording ? 'Stop Recording' : 'Record Audio';
    button.classList.toggle('is-recording', isRecording);
    button.title = supportsAudioRecording() ? (isRecording ? 'Stop and save voice note' : 'Record a voice note') : 'Audio recording is not supported in this browser';
  }

  async function toggleAudioRecording() {
    if (state.recorder) {
      stopAudioRecording();
      return;
    }
    await startAudioRecording();
  }

  async function startAudioRecording() {
    if (!state.currentBoard) return;
    if (!supportsAudioRecording()) {
      setStatus('Audio recording is not supported in this browser.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = preferredRecorderMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      state.recorderChunks = [];
      state.recorderStream = stream;
      state.recorder = recorder;

      recorder.addEventListener('dataavailable', (event) => {
        if (event.data && event.data.size > 0) state.recorderChunks.push(event.data);
      });

      recorder.addEventListener('stop', () => {
        finalizeAudioRecording(mimeType || recorder.mimeType || 'audio/webm').catch((error) => {
          setBadge('Error');
          setStatus(error.message || 'Audio recording failed');
        });
      });

      recorder.start();
      updateRecorderButton();
      setBadge('Recording');
      setStatus('Recording voice note… click Stop Recording when done.');
    } catch (error) {
      cleanupAudioRecorder();
      updateRecorderButton();
      setBadge('Error');
      setStatus(error?.name === 'NotAllowedError' ? 'Microphone permission was denied.' : (error.message || 'Could not start audio recording.'));
    }
  }

  function stopAudioRecording() {
    if (!state.recorder) return;
    try {
      if (state.recorder.state !== 'inactive') state.recorder.stop();
    } catch (error) {
      cleanupAudioRecorder();
      updateRecorderButton();
      setBadge('Error');
      setStatus(error.message || 'Could not stop recording.');
    }
  }

  async function finalizeAudioRecording(mimeType) {
    const chunks = state.recorderChunks.slice();
    cleanupAudioRecorder();
    updateRecorderButton();
    if (!chunks.length) {
      setStatus('No audio was captured.');
      return;
    }
    const cleanType = String(mimeType || 'audio/webm').split(';', 1)[0] || 'audio/webm';
    const extension = cleanType.includes('ogg') ? 'ogg' : 'webm';
    const blob = new Blob(chunks, { type: cleanType });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const file = new File([blob], `voice-note-${stamp}.${extension}`, { type: cleanType });
    setStatus('Saving recorded voice note…');
    await createAudioCardFromFile(file, {
      title: `Voice note ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`,
      content: 'Recorded on Board.',
    });
  }

  function cleanupAudioRecorder() {
    if (state.recorderStream) {
      state.recorderStream.getTracks().forEach((track) => track.stop());
    }
    state.recorder = null;
    state.recorderStream = null;
    state.recorderChunks = [];
  }

  function duplicateBoardItem(itemId) {
    if (!state.currentBoard) return;
    const source = state.currentBoard.items.find((item) => item.id === itemId);
    if (!source) return;
    const pos = nextCardPosition();
    const clone = Object.assign({}, JSON.parse(JSON.stringify(source)), {
      id: makeClientId('item'),
      title: `${source.title || (source.type === 'checklist' ? 'Checklist' : source.type === 'text' ? 'Text' : source.type === 'image' ? 'Image reference' : source.type === 'audio' ? 'Audio reference' : source.type === 'video' ? 'Video reference' : 'Sticky note')} Copy`,
      x: Number(source.x || pos.x) + 28,
      y: Number(source.y || pos.y) + 28,
      z: pos.z,
    });
    if (Array.isArray(clone.checked_items)) {
      clone.checked_items = clone.checked_items.map((task) => Object.assign({}, task, { id: makeClientId('check') }));
    }
    state.currentBoard.items.push(clone);
    state.selectedItemId = clone.id;
    queueSave('Duplicating card…', 0);
    renderCurrentBoard();
  }

  function deleteBoardItem(itemId) {
    if (!state.currentBoard) return;
    state.currentBoard.items = state.currentBoard.items.filter((item) => item.id !== itemId);
    pruneChecklistLinksForDeletedItem(itemId);
    if (state.selectedItemId === itemId) state.selectedItemId = '';
    queueSave('Deleting card…', 0);
    renderCurrentBoard();
  }

  function cloneBoardForSave(board) {
    if (board) ensureCanvasView(board);
    return JSON.parse(JSON.stringify(board || {}));
  }


  function queueRecoverySnapshot(delay) {
    if (!state.currentBoard || !state.currentBoard.id) return;
    window.clearTimeout(state.recoveryTimer);
    state.recoveryTimer = window.setTimeout(writeRecoverySnapshot, Number.isFinite(delay) ? delay : 900);
  }

  async function writeRecoverySnapshot() {
    if (!state.currentBoard || !state.currentBoard.id || !state.dirty) return;
    syncRenderedCardPositions();
    syncRenderedCardSizes();
    refreshLinkedCardColorInheritance();
    const snapshot = cloneBoardForSave(state.currentBoard);
    writeBrowserRecovery(snapshot);
    try {
      await api(`${API_ROOT}/${encodeURIComponent(snapshot.id)}/recovery`, {
        method: 'POST',
        body: JSON.stringify({ board: snapshot }),
      });
    } catch (_) {
      // Browser fallback already holds a temporary recovery snapshot if the local API is unavailable.
    }
  }

  async function clearRecoverySnapshot(boardId) {
    if (!boardId) return;
    window.clearTimeout(state.recoveryTimer);
    clearBrowserRecovery(boardId);
    try { await api(`${API_ROOT}/${encodeURIComponent(boardId)}/recovery`, { method: 'DELETE' }); } catch (_) {}
  }

  async function checkForRecoverySnapshot(board) {
    if (!board || !board.id) return board;
    let recovery = null;
    try {
      const payload = await api(`${API_ROOT}/${encodeURIComponent(board.id)}/recovery`);
      recovery = payload.recovery || null;
    } catch (_) {}
    try {
      const localRaw = localStorage.getItem(browserRecoveryKey(board.id));
      const localRecovery = localRaw ? JSON.parse(localRaw) : null;
      if (isRecoveryNewer(localRecovery, recovery?.board ? recovery.board : board)) recovery = localRecovery;
    } catch (_) {}
    if (!isRecoveryNewer(recovery, board)) return board;
    const time = formatSavedTime(recovery.saved_at || recovery.board?.updated_at) || 'recently';
    const restore = window.confirm(`Recovered unsaved Board changes from ${time}. Restore them?`);
    if (!restore) {
      await clearRecoverySnapshot(board.id);
      return board;
    }
    state.dirty = true;
    state.changeVersion += 1;
    setBadge('Recovered');
    setStatus('Recovered unsaved board changes. Saving restored board…');
    return ensureBoardShape(recovery.board);
  }

  function queueSave(message, delay) {
    if (!state.currentBoard) return;
    state.changeVersion += 1;
    state.dirty = true;
    setBadge('Unsaved');
    setStatus(message || 'Unsaved changes…');
    queueRecoverySnapshot(900);
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(saveCurrentBoard, Number.isFinite(delay) ? delay : 450);
  }

  async function saveCurrentBoard() {
    if (!state.currentBoard) return;
    if (state.saving) {
      state.pendingSave = true;
      return;
    }

    syncRenderedCardPositions();
    syncRenderedCardSizes();
    refreshLinkedCardColorInheritance();
    const saveVersion = state.changeVersion;
    const boardSnapshot = cloneBoardForSave(state.currentBoard);
    state.saving = true;
    state.pendingSave = false;
    setBadge('Saving');
    setStatus('Saving board…');

    try {
      const payload = await api(`${API_ROOT}/${encodeURIComponent(boardSnapshot.id)}`, {
        method: 'PUT',
        body: JSON.stringify({ board: boardSnapshot }),
      });

      state.boards = Array.isArray(payload.boards) ? payload.boards : state.boards;

      if (state.changeVersion === saveVersion && !state.pendingSave) {
        // Keep live board state after save so quick UI edits, like Add task, do not get replaced by a stale save response.
        const savedBoard = ensureBoardShape(payload.board || null);
        if (savedBoard && state.currentBoard) {
          state.currentBoard.created_at = savedBoard.created_at || state.currentBoard.created_at;
          state.currentBoard.updated_at = savedBoard.updated_at || state.currentBoard.updated_at;
          state.currentBoard.name = savedBoard.name || state.currentBoard.name;
        }
        state.dirty = false;
        state.lastSavedAt = state.currentBoard.updated_at || new Date().toISOString();
        state.saveError = '';
        clearRecoverySnapshot(state.currentBoard.id);
        setBadge('Saved');
        setStatus(`Saved at ${formatSavedTime(state.lastSavedAt) || 'now'} · ${state.currentBoard.items?.length || 0} items`);
      } else {
        state.dirty = true;
        setBadge('Unsaved');
        setStatus('Saving latest board changes…');
      }

      renderBoardPicker();
    } catch (error) {
      state.saveError = error.message || 'Save failed';
      state.dirty = true;
      setBadge('Save failed');
      setStatus(`${state.saveError} · Recovery snapshot kept`);
    } finally {
      state.saving = false;
      if (state.currentBoard && (state.pendingSave || state.changeVersion !== saveVersion)) {
        state.pendingSave = false;
        window.clearTimeout(state.saveTimer);
        state.saveTimer = window.setTimeout(saveCurrentBoard, 80);
      }
    }
  }

  async function loadBoardList(preferredId) {
    state.loading = true;
    setBadge('Loading');
    setStatus('Loading boards…');
    try {
      const payload = await api(API_ROOT);
      state.boards = Array.isArray(payload.boards) ? payload.boards : [];
      const nextId = preferredId || state.currentBoard?.id || state.boards[0]?.id || '';
      if (nextId) {
        await loadBoard(nextId, false);
      } else {
        state.currentBoard = null;
      }
      if (!state.currentBoard || !state.dirty) state.dirty = false;
      renderCurrentBoard();
    } catch (error) {
      state.currentBoard = null;
      setBadge('Error');
      setStatus(error.message || 'Could not load boards');
      renderCurrentBoard();
    } finally {
      state.loading = false;
    }
  }

  async function loadBoard(boardId, refreshList) {
    if (!boardId) return;
    setStatus('Loading board…');
    const payload = await api(`${API_ROOT}/${encodeURIComponent(boardId)}`);
    state.dirty = false;
    state.currentBoard = await checkForRecoverySnapshot(ensureBoardShape(payload.board || null));
    if (state.dirty) {
      queueSave('Saving recovered board…', 0);
    } else {
      state.lastSavedAt = state.currentBoard?.updated_at || '';
    }
    state.dirty = !!state.dirty;
    if (refreshList) await loadBoardList(boardId);
    else renderCurrentBoard();
  }

  async function createBoard(name) {
    setStatus('Creating board…');
    const payload = await api(API_ROOT, {
      method: 'POST',
      body: JSON.stringify({ name: name || 'Untitled Board' }),
    });
    state.boards = Array.isArray(payload.boards) ? payload.boards : state.boards;
    state.currentBoard = ensureBoardShape(payload.board || null);
    state.selectedItemId = '';
    state.dirty = false;
    await loadBoardList(state.currentBoard?.id);
  }

  async function renameCurrentBoard() {
    const input = $('board-name-input');
    if (!input || !state.currentBoard || state.renaming) return;
    const nextName = (input.value || '').trim() || 'Untitled Board';
    if (nextName === state.currentBoard.name) return;
    state.renaming = true;
    setStatus('Renaming…');
    try {
      const payload = await api(`${API_ROOT}/${encodeURIComponent(state.currentBoard.id)}/rename`, {
        method: 'PATCH',
        body: JSON.stringify({ name: nextName }),
      });
      state.currentBoard = ensureBoardShape(payload.board || state.currentBoard);
      state.boards = Array.isArray(payload.boards) ? payload.boards : state.boards;
      state.dirty = false;
      setStatus('Renamed');
      renderCurrentBoard();
    } catch (error) {
      input.value = state.currentBoard.name || 'Untitled Board';
      setStatus(error.message || 'Rename failed');
    } finally {
      state.renaming = false;
    }
  }

  async function duplicateCurrentBoard() {
    if (!state.currentBoard) return;
    setStatus('Duplicating board…');
    try {
      const source = state.currentBoard;
      const createPayload = await api(API_ROOT, {
        method: 'POST',
        body: JSON.stringify({ name: `${source.name || 'Untitled Board'} Copy` }),
      });
      const clone = Object.assign({}, source, {
        id: createPayload.board.id,
        name: createPayload.board.name,
        created_at: createPayload.board.created_at,
        updated_at: createPayload.board.updated_at,
      });
      const saved = await api(`${API_ROOT}/${encodeURIComponent(clone.id)}`, {
        method: 'PUT',
        body: JSON.stringify({ board: clone }),
      });
      state.currentBoard = ensureBoardShape(saved.board || createPayload.board);
      state.selectedItemId = '';
      state.dirty = false;
      await loadBoardList(state.currentBoard.id);
      setStatus('Duplicated');
    } catch (error) {
      setStatus(error.message || 'Duplicate failed');
    }
  }

  async function deleteCurrentBoard() {
    if (!state.currentBoard) return;
    const name = state.currentBoard.name || 'Untitled Board';
    if (!window.confirm(`Delete board "${name}"? This removes the local board record.`)) return;
    setStatus('Deleting board…');
    try {
      await api(`${API_ROOT}/${encodeURIComponent(state.currentBoard.id)}`, { method: 'DELETE' });
      state.currentBoard = null;
      state.selectedItemId = '';
      state.dirty = false;
      await loadBoardList();
      setStatus('Deleted');
    } catch (error) {
      setStatus(error.message || 'Delete failed');
    }
  }

  function bindBoardShell() {
    if (!document.body.dataset.boardDragBound) {
      document.body.dataset.boardDragBound = '1';
      document.addEventListener('pointermove', handleDocumentPointerMove);
      document.addEventListener('pointerup', handleDocumentPointerUp);
      document.addEventListener('pointercancel', handleDocumentPointerUp);
      window.addEventListener('keydown', (event) => {
        if (event.code !== 'Space' || isInteractiveTarget(event.target)) return;
        state.spacePanning = true;
        renderCanvasView();
      });
      window.addEventListener('keyup', (event) => {
        if (event.code !== 'Space') return;
        state.spacePanning = false;
        renderCanvasView();
      });
      window.addEventListener('beforeunload', (event) => {
        if (!state.currentBoard || !state.dirty) return;
        writeBrowserRecovery(state.currentBoard);
        event.preventDefault();
        event.returnValue = '';
      });
    }

    const picker = $('board-picker');
    if (picker && !picker.dataset.bound) {
      picker.dataset.bound = '1';
      picker.addEventListener('change', () => {
        state.selectedItemId = '';
        loadBoard(picker.value, false).catch((error) => setStatus(error.message));
      });
    }

    const newBtn = $('board-new-btn');
    if (newBtn && !newBtn.dataset.bound) {
      newBtn.dataset.bound = '1';
      newBtn.addEventListener('click', () => createBoard('Untitled Board').catch((error) => setStatus(error.message)));
    }

    const addStickyBtn = $('board-add-sticky');
    if (addStickyBtn && !addStickyBtn.dataset.bound) {
      addStickyBtn.dataset.bound = '1';
      addStickyBtn.addEventListener('click', createStickyNote);
    }

    const addChecklistBtn = $('board-add-checklist');
    if (addChecklistBtn && !addChecklistBtn.dataset.bound) {
      addChecklistBtn.dataset.bound = '1';
      addChecklistBtn.addEventListener('click', createChecklistCard);
    }

    const addTextBtn = $('board-add-text');
    if (addTextBtn && !addTextBtn.dataset.bound) {
      addTextBtn.dataset.bound = '1';
      addTextBtn.addEventListener('click', createTextNote);
    }

    const imageInput = $('board-image-file-input');
    const addImageBtn = $('board-add-image');
    if (addImageBtn && !addImageBtn.dataset.bound) {
      addImageBtn.dataset.bound = '1';
      addImageBtn.addEventListener('click', () => {
        if (imageInput) imageInput.click();
      });
    }
    if (imageInput && !imageInput.dataset.bound) {
      imageInput.dataset.bound = '1';
      imageInput.addEventListener('change', () => {
        const file = imageInput.files && imageInput.files[0];
        imageInput.value = '';
        createImageCardFromFile(file);
      });
    }

    const audioInput = $('board-audio-file-input');
    const addAudioBtn = $('board-add-audio');
    if (addAudioBtn && !addAudioBtn.dataset.bound) {
      addAudioBtn.dataset.bound = '1';
      addAudioBtn.addEventListener('click', () => {
        if (audioInput) audioInput.click();
      });
    }
    if (audioInput && !audioInput.dataset.bound) {
      audioInput.dataset.bound = '1';
      audioInput.addEventListener('change', () => {
        const file = audioInput.files && audioInput.files[0];
        audioInput.value = '';
        createAudioCardFromFile(file);
      });
    }

    const videoInput = $('board-video-file-input');
    const addVideoBtn = $('board-add-video');
    if (addVideoBtn && !addVideoBtn.dataset.bound) {
      addVideoBtn.dataset.bound = '1';
      addVideoBtn.addEventListener('click', () => {
        if (videoInput) videoInput.click();
      });
    }
    if (videoInput && !videoInput.dataset.bound) {
      videoInput.dataset.bound = '1';
      videoInput.addEventListener('change', () => {
        const file = videoInput.files && videoInput.files[0];
        videoInput.value = '';
        createVideoCardFromFile(file);
      });
    }

    const recordAudioBtn = $('board-record-audio');
    if (recordAudioBtn && !recordAudioBtn.dataset.bound) {
      recordAudioBtn.dataset.bound = '1';
      recordAudioBtn.addEventListener('click', () => {
        toggleAudioRecording().catch((error) => setStatus(error.message || 'Could not record audio'));
      });
    }

    const canvas = $('board-canvas');
    if (canvas && !canvas.dataset.panBound) {
      canvas.dataset.panBound = '1';
      canvas.addEventListener('pointerdown', handleCanvasPointerDown);
      canvas.addEventListener('wheel', (event) => {
        if (!state.currentBoard || (!event.ctrlKey && !event.metaKey)) return;
        event.preventDefault();
        const shell = canvas.closest('.board-canvas-shell');
        const rect = shell ? shell.getBoundingClientRect() : { left: 0, top: 0 };
        const factor = event.deltaY < 0 ? 1.1 : 0.9;
        setCanvasZoom(getCanvasZoom() * factor, { x: event.clientX - rect.left, y: event.clientY - rect.top });
      }, { passive: false });
    }

    const zoomOutBtn = $('board-zoom-out');
    if (zoomOutBtn && !zoomOutBtn.dataset.bound) {
      zoomOutBtn.dataset.bound = '1';
      zoomOutBtn.addEventListener('click', () => setCanvasZoom(getCanvasZoom() / 1.15));
    }

    const zoomInBtn = $('board-zoom-in');
    if (zoomInBtn && !zoomInBtn.dataset.bound) {
      zoomInBtn.dataset.bound = '1';
      zoomInBtn.addEventListener('click', () => setCanvasZoom(getCanvasZoom() * 1.15));
    }

    const zoomResetBtn = $('board-zoom-reset');
    if (zoomResetBtn && !zoomResetBtn.dataset.bound) {
      zoomResetBtn.dataset.bound = '1';
      zoomResetBtn.addEventListener('click', resetCanvasView);
    }

    const fitBtn = $('board-fit-content');
    if (fitBtn && !fitBtn.dataset.bound) {
      fitBtn.dataset.bound = '1';
      fitBtn.addEventListener('click', fitCanvasToContent);
    }

    const gridBtn = $('board-grid-toggle');
    if (gridBtn && !gridBtn.dataset.bound) {
      gridBtn.dataset.bound = '1';
      gridBtn.addEventListener('click', toggleCanvasGrid);
    }

    const duplicateBtn = $('board-duplicate-btn');
    if (duplicateBtn && !duplicateBtn.dataset.bound) {
      duplicateBtn.dataset.bound = '1';
      duplicateBtn.addEventListener('click', duplicateCurrentBoard);
    }

    const deleteBtn = $('board-delete-btn');
    if (deleteBtn && !deleteBtn.dataset.bound) {
      deleteBtn.dataset.bound = '1';
      deleteBtn.addEventListener('click', deleteCurrentBoard);
    }

    const nameInput = $('board-name-input');
    if (nameInput && !nameInput.dataset.bound) {
      nameInput.dataset.bound = '1';
      nameInput.addEventListener('blur', renameCurrentBoard);
      nameInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          nameInput.blur();
        }
      });
    }
  }

  function refreshBoardSurface() {
    const root = $('board-surface-root');
    if (!root) return;
    bindBoardShell();
    loadBoardList().catch((error) => {
      setBadge('Error');
      setStatus(error.message || 'Board shell failed to load');
    });
  }

  window.neoRefreshBoardSurface = refreshBoardSurface;
  document.addEventListener('DOMContentLoaded', refreshBoardSurface);
})();
