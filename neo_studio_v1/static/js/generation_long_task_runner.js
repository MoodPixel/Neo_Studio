(function () {
  function wait(ms) {
    return new Promise(resolve => window.setTimeout(resolve, ms));
  }

  function absoluteUrl(url) {
    const raw = String(url || '').trim();
    if (!raw) return '';
    try {
      return new URL(raw, window.location.origin).toString();
    } catch (_) {
      return raw;
    }
  }

  async function runPollingTask(options = {}) {
    const startUrl = absoluteUrl(options.startUrl);
    const buildStatusUrl = typeof options.buildStatusUrl === 'function' ? options.buildStatusUrl : (jobId => `${String(options.statusUrlBase || '').trim().replace(/\/$/, '')}/${encodeURIComponent(jobId)}`);
    const startFetch = options.startFetch || (window.safeFetchJson || null);
    const pollFetch = options.pollFetch || (window.safeFetchJson || null);
    const pollIntervalMs = Math.max(400, Number(options.pollIntervalMs || 1200));
    const onProgress = typeof options.onProgress === 'function' ? options.onProgress : (() => {});
    const onCompleted = typeof options.onCompleted === 'function' ? options.onCompleted : (() => {});
    const onSoftTimeout = typeof options.onSoftTimeout === 'function' ? options.onSoftTimeout : (() => {});
    const onError = typeof options.onError === 'function' ? options.onError : (() => {});

    if (!startUrl) throw new Error('Long task start URL is missing.');
    if (!startFetch || !pollFetch) throw new Error('Long task fetch helper is missing.');

    const startData = await startFetch(startUrl, options.startOptions || {});
    const jobId = String(startData.job_id || '').trim();
    if (!jobId) throw new Error(String(startData.message || 'Could not start the backend task.'));

    let lastPayload = startData;
    if (startData.message) onProgress(String(startData.message), startData);

    while (true) {
      await wait(pollIntervalMs);
      const statusUrl = absoluteUrl(`${buildStatusUrl(jobId)}?_=${Date.now()}`);
      lastPayload = await pollFetch(statusUrl, { cache:'no-store' });
      const state = String(lastPayload.state || '').trim().toLowerCase();
      const message = String(lastPayload.message || '').trim();
      if (message) onProgress(message, lastPayload);
      if (state === 'completed') {
        await onCompleted(lastPayload);
        return lastPayload;
      }
      if (state === 'timeout') {
        await onSoftTimeout(lastPayload);
        return lastPayload;
      }
      if (state === 'error') {
        const err = new Error(message || 'The backend task failed.');
        await onError(err, lastPayload);
        throw err;
      }
    }
  }

  window.NeoGenerationLongTasks = {
    wait,
    runPollingTask,
  };
})();
