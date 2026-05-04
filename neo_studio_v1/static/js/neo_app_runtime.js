(function () {
  const app = window.NeoStudioApp = window.NeoStudioApp || {};
  const generation = app.generation = app.generation || {};

  function ensureBucket(name) {
    if (!generation[name] || typeof generation[name] !== 'object') generation[name] = {};
    return generation[name];
  }

  function defineLegacyAlias(name) {
    const existing = Object.getOwnPropertyDescriptor(window, name);
    if (existing && existing.configurable === false) return false;
    try {
      Object.defineProperty(window, name, {
        configurable: true,
        enumerable: false,
        get() {
          return ensureBucket('legacy')[name];
        },
        set(value) {
          ensureBucket('legacy')[name] = value;
        },
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  generation.register = function registerGenerationBucket(name, entries) {
    const bucket = ensureBucket(name);
    if (entries && typeof entries === 'object') Object.assign(bucket, entries);
    return bucket;
  };

  generation.installLegacyAliases = function installGenerationLegacyAliases(entries) {
    const legacy = ensureBucket('legacy');
    Object.entries(entries || {}).forEach(([name, value]) => {
      defineLegacyAlias(name);
      legacy[name] = value;
      if (window[name] !== value) {
        try {
          window[name] = value;
        } catch (_) {
          // Ignore readonly global edge-cases; getter-backed alias still exists when defineProperty succeeded.
        }
      }
    });
    return legacy;
  };

  generation.setRuntime = function setGenerationRuntime(runtime) {
    generation.runtime = runtime || null;
    generation.installLegacyAliases({ NeoGenerationRuntime: generation.runtime });
    return generation.runtime;
  };

  generation.getRuntime = function getGenerationRuntime() {
    return generation.runtime || ensureBucket('legacy').NeoGenerationRuntime || window.NeoGenerationRuntime || null;
  };

  generation.getAction = function getGenerationAction(name) {
    if (!name) return null;
    const buckets = ['actions', 'handlers', 'preview', 'library', 'workflow', 'queue', 'legacy'];
    for (const bucketName of buckets) {
      const candidate = ensureBucket(bucketName)[name];
      if (candidate != null) return candidate;
    }
    return null;
  };

  generation.invoke = function invokeGenerationAction(name) {
    const fn = generation.getAction(name);
    if (typeof fn !== 'function') return null;
    return fn.apply(window, Array.prototype.slice.call(arguments, 1));
  };
})();
