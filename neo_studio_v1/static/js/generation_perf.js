(function () {
  const cache = new Map();

  function debounce(fn, wait = 180) {
    let timer = null;
    return function debounced(...args) {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        timer = null;
        fn.apply(this, args);
      }, wait);
    };
  }

  function writeCache(key, value) {
    cache.set(String(key), { value, at: Date.now() });
  }

  function readCache(key, maxAgeMs = 5000) {
    const entry = cache.get(String(key));
    if (!entry) return null;
    if ((Date.now() - Number(entry.at || 0)) > Number(maxAgeMs || 0)) {
      cache.delete(String(key));
      return null;
    }
    return entry.value;
  }

  function clearCache(key = '') {
    if (!key) {
      cache.clear();
      return;
    }
    cache.delete(String(key));
  }

  function lazyInitAccordion(accordionId, initFn) {
    const block = document.querySelector(`[data-accordion-id="${accordionId}"]`);
    if (!block || typeof initFn !== 'function') return;
    let done = false;
    const run = () => {
      if (done) return;
      done = true;
      try { initFn(); } catch (_) {}
    };
    if (block.open) run();
    block.addEventListener('toggle', () => { if (block.open) run(); });
  }

  window.NeoGenerationPerf = {
    debounce,
    readCache,
    writeCache,
    clearCache,
    lazyInitAccordion,
  };
})();
