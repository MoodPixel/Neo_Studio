(function () {
  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function $(id) {
    return document.getElementById(id);
  }

  function toneFromChip(chip) {
    const value = `${chip?.className || ''} ${chip?.textContent || ''}`.toLowerCase();
    if (value.includes('is-running') || /running|queued|processing|executing|monitoring|connecting/.test(value)) return 'running';
    if (value.includes('is-success') || /completed|success|ready/.test(value)) return 'success';
    if (value.includes('is-paused') || /paused|cancelled|interrupted|stopped/.test(value)) return 'paused';
    if (value.includes('is-error') || /error|failed|offline/.test(value)) return 'error';
    return 'idle';
  }

  function applyRunButtonTone() {
    const chip = $('generation-action-status-chip');
    const runBtn = $('btn-generation-run');
    if (!chip || !runBtn) return;
    const tone = toneFromChip(chip);
    runBtn.classList.remove('is-idle', 'is-running', 'is-success', 'is-paused', 'is-error');
    runBtn.classList.add(`is-${tone}`);
  }

  function boot() {
    const chip = $('generation-action-status-chip');
    if (!chip || chip.dataset.runToneBound === '1') {
      applyRunButtonTone();
      return;
    }
    const observer = new MutationObserver(() => applyRunButtonTone());
    observer.observe(chip, { attributes: true, attributeFilter: ['class'], childList: true, subtree: true, characterData: true });
    chip.dataset.runToneBound = '1';
    applyRunButtonTone();
  }

  document.addEventListener('neo-generation-layout-mounted', () => window.setTimeout(boot, 120));
  ready(() => boot());
})();
