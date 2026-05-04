(function () {
  const ROOT_SELECTOR = '#tab-generate';
  const ADVANCED_GROUPS = {
    defaults: ['btn-generation-set-default-snapshot', 'btn-generation-clear-default-snapshot'],
    manage: ['btn-generation-update-snapshot', 'btn-generation-rename-snapshot', 'btn-generation-duplicate-snapshot'],
    portability: ['btn-generation-export-snapshot', 'btn-generation-import-snapshot', 'generation-shell-snapshot-import-file'],
    danger: ['btn-generation-delete-snapshot']
  };

  const MODAL_NOTES = [
    {
      modalId: 'generation-prompt-manager-modal',
      text: 'Quick use inside Generation. Full prompt creation and long-term editing still belong in Prompt Studio.',
      label: 'Prompt source of truth'
    },
    {
      modalId: 'generation-save-prompt-modal',
      text: 'This is a quick-save route from the current run. Use Prompt Studio when you need the full prompt-management workflow.',
      label: 'Quick save only'
    },
    {
      modalId: 'generation-character-tool-modal',
      text: 'Use this to assemble or insert a character for the current image flow. Manage saved character records in Prompt Studio.',
      label: 'Quick use only'
    },
    {
      modalId: 'generation-keyword-tool-modal',
      text: 'Use this to insert reusable prompt fragments into the current run. Manage keyword records in Library.',
      label: 'Quick use only'
    },
    {
      modalId: 'generation-caption-tool-modal',
      text: 'Use this to reuse saved captions in the current run. Manage caption records in Caption Studio or Library.',
      label: 'Quick use only'
    }
  ];

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) {
    return document.getElementById(id);
  }

  function createInfoNote(label, text) {
    const note = document.createElement('div');
    note.className = 'generation-ownership-note';
    note.innerHTML = `
      <div class="generation-ownership-note-label">${label}</div>
      <div class="generation-ownership-note-copy">${text}</div>`;
    return note;
  }

  function applyModalNotes() {
    MODAL_NOTES.forEach(item => {
      const modal = $(item.modalId);
      const body = modal?.querySelector(':scope .modal-body');
      if (!body || body.querySelector('.generation-ownership-note')) return;
      body.prepend(createInfoNote(item.label, item.text));
    });
  }

  function ensurePresetManagerModal() {
    let modal = $('generation-preset-manager-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'generation-preset-manager-modal';
    modal.className = 'modal-backdrop hidden';
    modal.innerHTML = `
      <div class="modal-shell modal-md generation-preset-manager-shell">
        <div class="modal-header">
          <div>
            <h3 style="margin:0;">Workspace Preset Manager</h3>
            <div class="muted small">Keep the header focused on save/load. Use this panel for default, rename, duplicate, import/export, and delete actions.</div>
          </div>
          <button class="modal-close" id="btn-close-generation-preset-manager" type="button">×</button>
        </div>
        <div class="modal-body generation-preset-manager-body">
          <div class="generation-ownership-note">
            <div class="generation-ownership-note-label">Generation owns workspace presets</div>
            <div class="generation-ownership-note-copy">Workspace presets are the saved state of the current Generation workspace. Prompt presets and caption presets belong to their own authoring surfaces.</div>
          </div>
          <div class="generation-preset-manager-grid">
            <div class="generation-preset-manager-card">
              <div class="stat-title">Default startup</div>
              <div class="muted small">Choose whether the selected workspace preset auto-loads when Neo starts.</div>
              <div class="generation-preset-manager-actions" id="generation-preset-manager-defaults"></div>
            </div>
            <div class="generation-preset-manager-card">
              <div class="stat-title">Manage selected preset</div>
              <div class="muted small">Update, rename, or duplicate the workspace preset currently selected in the header.</div>
              <div class="generation-preset-manager-actions" id="generation-preset-manager-manage"></div>
            </div>
            <div class="generation-preset-manager-card">
              <div class="stat-title">Portability</div>
              <div class="muted small">Move workspace presets between builds with export and import.</div>
              <div class="generation-preset-manager-actions" id="generation-preset-manager-portability"></div>
            </div>
            <div class="generation-preset-manager-card danger-zone">
              <div class="stat-title">Delete</div>
              <div class="muted small">Remove the selected workspace preset only after confirming it is not your default keeper.</div>
              <div class="generation-preset-manager-actions" id="generation-preset-manager-danger"></div>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
    return modal;
  }

  function bindPresetManagerModal() {
    const modal = ensurePresetManagerModal();
    const openBtn = $('btn-generation-open-preset-manager');
    const closeBtn = $('btn-close-generation-preset-manager');
    if (!modal || !openBtn || openBtn.dataset.modalBound === '1') return;
    const close = () => {
      modal.classList.add('hidden');
      const anyOpen = Array.from(document.querySelectorAll('.modal-backdrop')).some(node => !node.classList.contains('hidden'));
      document.body.classList.toggle('modal-open', anyOpen);
    };
    openBtn.addEventListener('click', event => {
      event.preventDefault();
      modal.classList.remove('hidden');
      document.body.classList.add('modal-open');
    });
    closeBtn?.addEventListener('click', close);
    modal.addEventListener('click', event => { if (event.target === modal) close(); });
    window.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !modal.classList.contains('hidden')) close();
    });
    openBtn.dataset.modalBound = '1';
  }

  function moveButtonsToModal() {
    Object.entries(ADVANCED_GROUPS).forEach(([groupKey, ids]) => {
      const host = $(`generation-preset-manager-${groupKey}`);
      if (!host) return;
      ids.forEach(id => {
        const node = $(id);
        if (!node) return;
        if (node.parentElement !== host) host.appendChild(node);
      });
    });
  }

  function compactPresetToolbar() {
    const root = document.querySelector(ROOT_SELECTOR);
    const toolbar = root?.querySelector('.generation-global-panel .row.u-gap-8.u-wrap.u-justify-end');
    const saveBtn = $('btn-generation-save-snapshot');
    const loadBtn = $('btn-generation-load-snapshot');
    const select = $('generation-shell-snapshot-select');
    if (!toolbar || !saveBtn || !loadBtn || !select) return false;

    saveBtn.textContent = 'Save preset';
    saveBtn.title = 'Save the current Generation workspace as a workspace preset';
    loadBtn.textContent = 'Load';
    loadBtn.title = 'Load the selected workspace preset';
    select.title = 'Workspace presets';

    let manageBtn = $('btn-generation-open-preset-manager');
    if (!manageBtn) {
      manageBtn = document.createElement('button');
      manageBtn.id = 'btn-generation-open-preset-manager';
      manageBtn.className = 'btn btn-small';
      manageBtn.type = 'button';
      manageBtn.textContent = 'Manage presets';
      manageBtn.title = 'Open the workspace preset manager';
    }

    if (manageBtn.parentElement !== toolbar) {
      toolbar.insertBefore(manageBtn, loadBtn.nextSibling);
    }
    toolbar.classList.add('generation-preset-toolbar-compact');
    return true;
  }

  function boot(attempt = 0) {
    if (!compactPresetToolbar()) {
      if (attempt < 40) window.setTimeout(() => boot(attempt + 1), 150);
      return;
    }
    ensurePresetManagerModal();
    moveButtonsToModal();
    bindPresetManagerModal();
    applyModalNotes();
  }

  ready(() => boot(0));
})();
