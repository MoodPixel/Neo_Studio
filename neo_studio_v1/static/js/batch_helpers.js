let currentInterruptedBatchJobId = '';
let recentBatchJobIndex = {};
let lastBatchTitleUpdateAt = 0;
const suppressedInterruptedBatchIds = new Set(JSON.parse(window.sessionStorage.getItem('neo-studio-suppressed-interrupted') || '[]'));

function persistSuppressedInterruptedBatchIds() {
  window.sessionStorage.setItem('neo-studio-suppressed-interrupted', JSON.stringify(Array.from(suppressedInterruptedBatchIds)));
}

function resetWindowBatchTitle() {
  document.title = window.NEO_STUDIO_BASE_TITLE || 'Neo Studio';
  lastBatchTitleUpdateAt = 0;
}

function formatCompactEta(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (!total) return '';
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${secs}s`;
}

function updateWindowBatchTitle(data) {
  const base = window.NEO_STUDIO_BASE_TITLE || 'Neo Studio';
  const status = data?.status || '';
  if (!data || ['completed', 'failed', 'cancelled'].includes(status)) {
    resetWindowBatchTitle();
    return;
  }
  const now = Date.now();
  if (now - lastBatchTitleUpdateAt < 1500) return;
  lastBatchTitleUpdateAt = now;
  const current = Number(data.current_index || 0);
  const total = Number(data.total_items || 0);
  const percent = Math.max(0, Math.round(Number(data.progress_percent || 0)));
  const processed = Number(data.processed || 0);
  const eta = Number(data.eta_seconds || 0);
  let detail = 'Batch running';
  if (status === 'interrupted') {
    detail = 'Resume available';
  } else if (total > 0 && processed >= 2 && eta > 0) {
    detail = `${current}/${total} • ETA ${formatCompactEta(eta)}`;
  } else if (status === 'cancelling') {
    detail = `${current}/${total || 0} • Stopping...`;
  } else if (total > 0) {
    detail = `${percent}%`;
  }
  document.title = `${base} — ${detail}`;
}

function resetBatchDisplay() {
  $('batch-progress-fill').style.width = '0%';
  $('batch-progress-text').textContent = 'Processing 0 / 0';
  $('batch-elapsed-total').textContent = 'Batch total: 00:00';
  $('batch-elapsed-current').textContent = 'Current file: 00:00';
  if ($('batch-eta')) $('batch-eta').textContent = 'ETA: —';
  $('batch-current-file').textContent = 'Current file: —';
  $('batch-counts').textContent = 'Success: 0 · Failed: 0 · Skipped: 0';
  if ($('batch-duplicate-summary')) $('batch-duplicate-summary').textContent = 'Duplicates: 0';
  if ($('batch-post-action-status')) $('batch-post-action-status').textContent = 'Post-task action: none';
  if ($('batch-output-summary')) $('batch-output-summary').textContent = 'Output folder: —';
  if ($('batch-logfile-summary')) $('batch-logfile-summary').textContent = 'Dataset log: —';
  resetWindowBatchTitle();
}

function refreshBatchSessionOptions(jobs, selected='') {
  const sel = $('batch-session-select');
  if (!sel) return;
  const items = Array.isArray(jobs) ? jobs : [];
  recentBatchJobIndex = {};
  sel.innerHTML = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = '—';
  sel.appendChild(first);
  items.forEach(job => {
    recentBatchJobIndex[job.job_id || ''] = job;
    const opt = document.createElement('option');
    opt.value = job.job_id || '';
    const folder = job.folder_path || 'Unknown folder';
    const prefix = job.interrupted || job.status === 'interrupted' ? '⚠ interrupted' : (job.status || 'saved');
    opt.textContent = `${prefix} · ${folder} · ${job.processed || 0}/${job.total_items || 0}`;
    if ((job.job_id || '') === selected) opt.selected = true;
    sel.appendChild(opt);
  });
  syncInterruptedBatchBanner(items);
}

function updateBatchActionButtons(data) {
  const status = data?.status || '';
  const running = status === 'running' || status === 'queued' || status === 'cancelling';
  const textConnected = typeof window.isBackendRoleConnected === 'function' ? window.isBackendRoleConnected('text') : false;
  if ($('btn-batch-cancel')) $('btn-batch-cancel').disabled = !(running || status === 'interrupted');
  if ($('btn-run-batch')) $('btn-run-batch').disabled = running || !textConnected;
  const hasFailed = Array.isArray(data?.failed_items) && data.failed_items.length > 0;
  if ($('btn-batch-retry')) $('btn-batch-retry').disabled = !textConnected || !currentBatchJobId || !hasFailed;
  const hasRemaining = Number(data?.remaining_items_count || 0) > 0 || status === 'cancelled' || status === 'interrupted';
  if ($('btn-batch-resume')) $('btn-batch-resume').disabled = !textConnected || !currentBatchJobId || !hasRemaining;
  const canCancelPost = Number(data?.post_action_seconds_left || 0) > 0;
  if ($('btn-batch-cancel-post-action')) $('btn-batch-cancel-post-action').disabled = !canCancelPost;
}

function updateBatchDisplay(data) {
  const pct = Math.max(0, Math.min(100, Number(data.progress_percent || 0)));
  $('batch-progress-fill').style.width = `${pct}%`;
  $('batch-progress-text').textContent = `Processing ${data.current_index || 0} / ${data.total_items || 0}`;
  $('batch-elapsed-total').textContent = `Batch total: ${formatElapsed(data.elapsed_total_seconds || 0)}`;
  $('batch-elapsed-current').textContent = `Current file: ${formatElapsed(data.elapsed_current_seconds || 0)}`;
  if ($('batch-eta')) {
    const eta = Number(data.eta_seconds || 0);
    $('batch-eta').textContent = eta > 0 ? `ETA: ${formatElapsed(eta)}` : 'ETA: —';
  }
  $('batch-current-file').textContent = `Current file: ${data.current_item_name || '—'}`;
  $('batch-counts').textContent = `Success: ${data.saved || 0} · Failed: ${data.errors || 0} · Skipped: ${data.skipped || 0}`;
  if ($('batch-duplicate-summary')) $('batch-duplicate-summary').textContent = `Duplicates: ${data.duplicates || 0}`;
  let postActionText = `Post-task action: ${data.post_action || 'none'}`;
  if (Number(data.post_action_seconds_left || 0) > 0) {
    postActionText += ` · ${data.post_action_status || 'countdown'} in ${data.post_action_seconds_left}s`;
  } else if (data.post_action_status && data.post_action_status !== 'idle') {
    postActionText += ` · ${data.post_action_status}`;
  }
  if ($('batch-post-action-status')) $('batch-post-action-status').textContent = postActionText;
  if ($('batch-output-summary')) $('batch-output-summary').textContent = `Output folder: ${data?.params?.output_folder || '—'}`;
  if ($('batch-logfile-summary')) $('batch-logfile-summary').textContent = `Dataset log: ${data?.dataset_log_path || '—'}`;
  const lines = [];
  if (data.message) lines.push(data.message);
  if (data.status === 'interrupted' && Number(data.remaining_items_count || 0) > 0) {
    lines.push(`Resume ready: ${data.remaining_items_count} item(s) still pending.`);
  }
  if (data.duplicate_lines?.length) {
    lines.push('');
    lines.push('Duplicate summary');
    data.duplicate_lines.forEach(x => lines.push(x));
  }
  (data.detail_lines || []).forEach(x => lines.push(x));
  if (data.error_lines?.length) {
    lines.push('');
    lines.push('Errors');
    data.error_lines.forEach(x => lines.push(x));
  }
  if (Array.isArray(data.failed_items) && data.failed_items.length) {
    lines.push('');
    lines.push('Failed files');
    data.failed_items.forEach(x => lines.push(x));
  }
  $('batch-log').value = lines.join('\n');
  refreshBatchSessionOptions(data.recent_jobs || [], data.job_id || currentBatchJobId || '');
  updateBatchActionButtons(data);
  updateWindowBatchTitle(data);
}

function stopBatchPolling() {
  if (batchPollHandle) {
    clearInterval(batchPollHandle);
    batchPollHandle = null;
  }
}

function pickInterruptedBatchJob(jobs) {
  const items = Array.isArray(jobs) ? jobs : [];
  return items.find(job => ((job?.status || '') === 'interrupted' || !!job?.interrupted) && !suppressedInterruptedBatchIds.has(job.job_id || '')) || null;
}

function syncInterruptedBatchBanner(jobs) {
  const banner = $('batch-interrupted-banner');
  if (!banner) return;
  const job = pickInterruptedBatchJob(jobs);
  if (!job) {
    banner.classList.add('hidden');
    currentInterruptedBatchJobId = '';
    if ($('batch-interrupted-summary')) $('batch-interrupted-summary').textContent = '';
    return;
  }
  currentInterruptedBatchJobId = job.job_id || '';
  const summary = $('batch-interrupted-summary');
  if (summary) {
    const parts = [job.folder_path || 'Unknown folder', `${job.processed || 0}/${job.total_items || 0} done`];
    if (job.errors) parts.push(`${job.errors} failed`);
    if (job.output_folder) parts.push(`out: ${job.output_folder}`);
    summary.textContent = parts.join(' · ');
  }
  banner.classList.remove('hidden');
  const textConnected = typeof window.isBackendRoleConnected === 'function' ? window.isBackendRoleConnected('text') : false;
  if ($('btn-interrupted-batch-resume')) $('btn-interrupted-batch-resume').disabled = !textConnected;
  if ($('btn-interrupted-batch-start-fresh')) $('btn-interrupted-batch-start-fresh').disabled = !textConnected;
}

async function refreshRecentBatchJobs() {
  try {
    const data = await safeFetchJson('/api/caption-batch-recent');
    refreshBatchSessionOptions(data.jobs || [], currentBatchJobId || '');
  } catch (_e) {}
}

async function fetchBatchJobStatus(jobId) {
  if (!jobId) throw new Error('No batch selected.');
  return safeFetchJson(`/api/caption-batch-status?job_id=${encodeURIComponent(jobId)}`);
}

function prefillBatchFormFromParams(params) {
  if (!params) return;
  if ($('batch-mode') && params.mode) $('batch-mode').value = params.mode;
  if ($('batch-folder')) $('batch-folder').value = params.folder_path || '';
  if ($('batch-output-folder')) $('batch-output-folder').value = params.output_folder || '';
  if ($('batch-extensions')) $('batch-extensions').value = Array.isArray(params.include_exts) ? params.include_exts.join(', ') : '';
  if ($('batch-recursive')) $('batch-recursive').checked = !!params.recursive;
  if ($('batch-post-action')) $('batch-post-action').value = params.post_task_action || 'none';
  if ($('batch-category')) fillCategorySelect('batch-category', initialCategories, params.category || initialLastCaptionCategory);
  if ($('batch-category-new')) $('batch-category-new').value = '';
  if ($('batch-base-name')) $('batch-base-name').value = params.base_name || 'Batch_Caption';
  if ($('batch-library-number-start')) $('batch-library-number-start').value = params.numbering_start || 1;
  if ($('batch-number-start')) $('batch-number-start').value = params.numbering_start || 1;
  if ($('batch-overwrite')) $('batch-overwrite').checked = !!params.overwrite_existing;
  if ($('batch-skip-existing')) $('batch-skip-existing').checked = !!params.dataset_skip_processed;
  if ($('batch-skip-duplicates')) $('batch-skip-duplicates').checked = !!params.skip_duplicates;
  if ($('batch-dataset-caption-images')) $('batch-dataset-caption-images').checked = !!params.dataset_caption_images;
  if ($('batch-dataset-save-txt')) $('batch-dataset-save-txt').checked = !!params.dataset_save_txt;
  if ($('batch-dataset-rename-images')) $('batch-dataset-rename-images').checked = !!params.dataset_rename_images;
  if ($('batch-dataset-transfer-mode')) $('batch-dataset-transfer-mode').value = params.dataset_transfer_mode || 'copy';
  if ($('batch-dataset-prefix')) $('batch-dataset-prefix').value = params.dataset_name_prefix || 'character';
  if ($('batch-dataset-pattern')) $('batch-dataset-pattern').value = params.dataset_name_pattern || '{prefix}_{num}';
  if ($('batch-dataset-number-padding')) $('batch-dataset-number-padding').value = params.dataset_number_padding || 4;
  if ($('batch-dataset-log-format')) $('batch-dataset-log-format').value = params.dataset_log_format || 'csv';
  toggleBatchMode();
  if (typeof syncDatasetPreparationControls === 'function') syncDatasetPreparationControls();
}

async function handleInterruptedBatchAction(action) {
  const jobId = currentInterruptedBatchJobId;
  if (!jobId) {
    setStatus('batch-status', 'No interrupted batch session found.', 'warn');
    return;
  }
  if (action === 'resume') {
    suppressedInterruptedBatchIds.delete(jobId);
    persistSuppressedInterruptedBatchIds();
    if ($('batch-session-select')) $('batch-session-select').value = jobId;
    currentBatchJobId = jobId;
    await resumeBatchCaption();
    return;
  }
  if (action === 'open_log') {
    if ($('batch-session-select')) $('batch-session-select').value = jobId;
    currentBatchJobId = jobId;
    await exportBatchLog();
    return;
  }
  if (action === 'start_fresh') {
    try {
      const data = await fetchBatchJobStatus(jobId);
      prefillBatchFormFromParams(data.params || {});
      suppressedInterruptedBatchIds.add(jobId);
      persistSuppressedInterruptedBatchIds();
      setStatus('batch-status', 'Interrupted session loaded into the form. Click Run batch to start fresh.', 'warn');
      $('batch-interrupted-banner')?.classList.add('hidden');
    } catch (e) {
      setStatus('batch-status', e.message, 'error');
    }
    return;
  }
  if (action === 'cancel') {
    const fd = new FormData();
    fd.append('job_id', jobId);
    try {
      const data = await safeFetchJson('/api/caption-batch-cancel', { method:'POST', body:fd });
      suppressedInterruptedBatchIds.delete(jobId);
      persistSuppressedInterruptedBatchIds();
      updateBatchDisplay(data);
      setStatus('batch-status', data.message || 'Interrupted batch dismissed.');
      await refreshRecentBatchJobs();
    } catch (e) {
      setStatus('batch-status', e.message, 'error');
    }
  }
}

async function pollBatchStatus() {
  if (!currentBatchJobId) return;
  try {
    const data = await safeFetchJson(`/api/caption-batch-status?job_id=${encodeURIComponent(currentBatchJobId)}`);
    updateBatchDisplay(data);
    setStatus('batch-status', data.message || data.summary || 'Batch running...');
    if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
      stopBatchPolling();
      setBusy('btn-run-batch', false);
      resetWindowBatchTitle();
      if (data.stats) updateStats(data.stats);
      if (data.categories) fillCategorySelect('batch-category', data.categories, resolveCategory('batch-category','batch-category-new'));
    }
  } catch (e) {
    stopBatchPolling();
    setBusy('btn-run-batch', false);
    resetWindowBatchTitle();
    setStatus('batch-status', e.message, 'error');
  }
}
