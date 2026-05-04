
function getRoleSession(role) {
  if (typeof window.getBackendRoleState === 'function') return window.getBackendRoleState(role) || { state:'offline', connected:false };
  return { state:'offline', connected:false };
}

function setButtonsDisabled(ids, disabled) {
  (ids || []).forEach(id => {
    const el = $(id);
    if (!el) return;
    if (id === 'btn-batch-cancel' || id === 'btn-batch-cancel-post-action') return;
    if (disabled) el.setAttribute('disabled', 'disabled');
    else if (!el.dataset.keepDisabled) el.removeAttribute('disabled');
  });
}

function updateBackendRequiredNote(noteId, bodyId, connected, onlineText, offlineText) {
  const note = $(noteId);
  const body = $(bodyId);
  if (!note || !body) return;
  note.classList.toggle('offline', !connected);
  note.classList.toggle('connected', !!connected);
  body.textContent = connected ? onlineText : offlineText;
}

let generationCatalogLoaded = false;
let generationCatalogSourceKey = '';
let lastGenerationJobId = '';
let generationPollTimer = null;
let generationActivePollJobId = '';

const generationFallbackSamplers = [
  'euler', 'euler_ancestral', 'dpmpp_2m', 'dpmpp_sde', 'dpmpp_2m_sde', 'dpmpp_3m_sde',
  'lcm', 'lms', 'heun', 'dpm_2', 'res_multistep', 'uni_pc', 'ddim', 'plms',
];
const generationFallbackSchedulers = [
  'normal', 'karras', 'exponential', 'polyexponential', 'simple', 'sgm_uniform',
  'linear_quadratic', 'kl_optimal', 'ddim_uniform', 'beta', 'turbo',
];

const generationResizeMethodOptions = [
  { value:'lanczos', label:'Lanczos' },
  { value:'bicubic', label:'Bicubic' },
  { value:'bilinear', label:'Bilinear' },
  { value:'area', label:'Area' },
  { value:'nearest-exact', label:'Nearest exact' },
];
const generationSupirColorFixOptions = [
  { value:'Wavelet', label:'Wavelet' },
  { value:'AdaIn', label:'AdaIn' },
  { value:'None', label:'None' },
];

const generationPreprocessorOptions = [
  { value:'none', label:'None · use image as-is' },
  { value:'canny', label:'Canny · Aux / OpenCV crisp edges' },
  { value:'softedge', label:'Soft Edge / HED · Aux gentle contours' },
  { value:'lineart', label:'Lineart · Aux clean black/white edges' },
  { value:'lineart_anime', label:'Lineart Anime · Aux anime/manga outlines' },
  { value:'scribble', label:'Scribble / Sketch · Aux rough guide map' },
  { value:'openpose', label:'OpenPose / DWPose · Aux pose skeleton map' },
  { value:'depth', label:'DepthAnythingV2 · Aux depth map' },
  { value:'normalbae', label:'NormalBae · Aux normal map' },
  { value:'tile', label:'Tile / Detail · use image as-is' },
  { value:'threshold', label:'Threshold · local hard black/white mask' },
  { value:'invert', label:'Invert · local quick reverse values' },
];
const generationControlnetUnitOptions = [
  { value:'auto', label:'Auto · no unit filter' },
  { value:'canny', label:'Canny' },
  { value:'softedge', label:'Soft Edge / HED' },
  { value:'lineart', label:'Lineart' },
  { value:'lineart_anime', label:'Lineart Anime' },
  { value:'scribble', label:'Scribble / Sketch' },
  { value:'openpose', label:'OpenPose / DWPose' },
  { value:'depth', label:'Depth / DepthAnythingV2' },
  { value:'normalbae', label:'Normal / NormalBae' },
  { value:'tile', label:'Tile / Detail' },
];
const generationIpAdapterWeightTypeOptions = [
  { value:'linear', label:'Linear' },
  { value:'ease in', label:'Ease In' },
  { value:'ease out', label:'Ease Out' },
  { value:'ease in-out', label:'Ease In-Out' },
  { value:'reverse in-out', label:'Reverse In-Out' },
  { value:'weak input', label:'Weak Input' },
  { value:'weak output', label:'Weak Output' },
  { value:'weak middle', label:'Weak Middle' },
  { value:'strong middle', label:'Strong Middle' },
  { value:'style transfer', label:'Style Transfer' },
  { value:'composition', label:'Composition' },
  { value:'strong style transfer', label:'Strong Style Transfer' },
  { value:'style and composition', label:'Style + Composition' },
  { value:'strong style and composition', label:'Strong Style + Composition' },
];
const generationIpAdapterCombineOptions = [
  { value:'concat', label:'Concat' },
  { value:'add', label:'Add' },
  { value:'subtract', label:'Subtract' },
  { value:'average', label:'Average' },
  { value:'norm average', label:'Norm Average' },
];
const generationIpAdapterEmbedScalingOptions = [
  { value:'V only', label:'V only' },
  { value:'K+V', label:'K+V' },
  { value:'K+V w/ C penalty', label:'K+V w/ C penalty' },
  { value:'K+mean(V) w/ C penalty', label:'K+mean(V) w/ C penalty' },
];
const generationIpAdapterModeOptions = [
  { value:'standard', label:'Standard' },
  { value:'faceid', label:'FaceID / FaceID Plus' },
];
const generationIpAdapterFaceIdPresetOptions = [
  { value:'FACEID', label:'FACEID' },
  { value:'FACEID PLUS - SD1.5 only', label:'FACEID PLUS · SD1.5 only' },
  { value:'FACEID PLUS V2', label:'FACEID PLUS V2' },
  { value:'FACEID PORTRAIT (style transfer)', label:'FACEID PORTRAIT · style transfer' },
  { value:'FACEID PORTRAIT UNNORM - SDXL only (strong)', label:'FACEID PORTRAIT UNNORM · SDXL only' },
];
const generationIpAdapterFaceIdProviderOptions = [
  { value:'CUDA', label:'CUDA' },
  { value:'CPU', label:'CPU' },
  { value:'ROCM', label:'ROCM' },
  { value:'DirectML', label:'DirectML' },
  { value:'OpenVINO', label:'OpenVINO' },
  { value:'CoreML', label:'CoreML' },
];
const generationIpAdapterOptionHelp = {
  mode: {
    standard: 'Standard mode uses the selected IP-Adapter model plus CLIP Vision and one or more reference images.',
    faceid: 'FaceID mode switches to the FaceID pipeline so identity comes from InsightFace + the FaceID preset + your references.'
  },
  weight_type: {
    linear: 'Balanced default. Keeps the reference influence steady across the run.',
    'ease in': 'Starts lighter and ramps up later in the denoise process.',
    'ease out': 'Starts stronger early and eases off later.',
    'ease in-out': 'Gentle at the start and end, stronger through the middle.',
    'reverse in-out': 'Stronger at the edges of the run and weaker in the middle.',
    'weak input': 'Less influence in the early noisy stage.',
    'weak output': 'Less influence near the final cleanup stage.',
    'weak middle': 'Less influence in the middle of the run.',
    'strong middle': 'More influence in the middle of the run.',
    'style transfer': 'Pushes more of the reference look, texture, and overall style.',
    composition: 'Pushes pose, framing, and layout more than raw texture.',
    'strong style transfer': 'A more aggressive style-borrowing preset.',
    'style and composition': 'Mixes both style borrowing and layout steering.',
    'strong style and composition': 'A harder push on both style and composition.'
  },
  combine_embeds: {
    concat: 'Best default for multiple references. Keeps each reference embedding more distinct instead of flattening them together.',
    add: 'Adds reference embeddings together for a stronger blend. Can get aggressive fast.',
    subtract: 'Uses the first reference against the others. More experimental than general-purpose.',
    average: 'Blends multiple references evenly into one average embedding.',
    'norm average': 'Normalizes references before averaging so one image does not dominate as easily.'
  },
  embeds_scaling: {
    'V only': 'Safest default. Usually the least chaotic way to apply the reference.',
    'K+V': 'Stronger reference lock because both key and value paths are pushed.',
    'K+V w/ C penalty': 'Stronger guidance with extra restraint to reduce overpowering.',
    'K+mean(V) w/ C penalty': 'A smoother, more stabilized strong-guidance mode.'
  },
  faceid_preset: {
    'FACEID': 'Base FaceID preset. Use it with the matching FACEID model family.',
    'FACEID PLUS - SD1.5 only': 'FaceID Plus preset for SD 1.5 only.',
    'FACEID PLUS V2': 'Best general FaceID Plus choice when you have the plusv2 FaceID model and matching LoRA.',
    'FACEID PORTRAIT (style transfer)': 'Portrait-oriented FaceID preset that leans more into style transfer.',
    'FACEID PORTRAIT UNNORM - SDXL only (strong)': 'A stronger SDXL portrait variant that can hit harder on the reference.'
  },
  faceid_provider: {
    CUDA: 'Uses GPU ONNX runtime. Fastest when onnxruntime-gpu is installed and working.',
    CPU: 'Slow but reliable fallback when CUDA or other GPU runtimes are acting cursed.',
    ROCM: 'AMD ROCm runtime path when your environment supports it.',
    DirectML: 'Windows DirectML runtime path for supported GPUs.',
    OpenVINO: 'Intel OpenVINO runtime path for supported hardware.',
    CoreML: 'Apple CoreML runtime path for supported hardware.'
  }
};

function getGenerationIpAdapterOptionHelp(category, value) {
  const key = String(value || '').trim();
  const categoryMap = generationIpAdapterOptionHelp[category] || {};
  return categoryMap[key] || 'This option changes how the IP-Adapter reference is applied. Keep it simple unless you are intentionally experimenting.';
}

function updateGenerationIpAdapterOptionExplainer(target, category, value) {
  if (!target) return;
  target.textContent = getGenerationIpAdapterOptionHelp(category, value);
}

function getGenerationIpAdapterRefCount(input) {
  return Array.isArray(input?.files) ? input.files.length : Number(input?.files?.length || 0);
}

function formatGenerationIpAdapterRefLabel(input) {
  const count = getGenerationIpAdapterRefCount(input);
  if (!count) return 'no reference image yet';
  if (count === 1) return input?.files?.[0]?.name || '1 ref image';
  const firstName = input?.files?.[0]?.name || 'reference image';
  return `${count} refs · first: ${firstName}`;
}

function bindGenerationIpAdapterExplainers(scope, explainer) {
  if (!scope || !explainer) return;
  const bindings = [
    ['mode', '.generation-ipadapter-mode, #generation-ipadapter-mode'],
    ['weight_type', '.generation-ipadapter-weight-type, #generation-ipadapter-weight-type'],
    ['combine_embeds', '.generation-ipadapter-combine-embeds, #generation-ipadapter-combine-embeds'],
    ['embeds_scaling', '.generation-ipadapter-embeds-scaling, #generation-ipadapter-embeds-scaling'],
    ['faceid_preset', '.generation-ipadapter-faceid-preset, #generation-ipadapter-faceid-preset'],
    ['faceid_provider', '.generation-ipadapter-faceid-provider, #generation-ipadapter-faceid-provider'],
  ];
  bindings.forEach(([category, selector]) => {
    const field = scope.querySelector(selector);
    if (!field || field.dataset.ipadapterExplainBound === 'true') return;
    field.dataset.ipadapterExplainBound = 'true';
    field.addEventListener('change', () => updateGenerationIpAdapterOptionExplainer(explainer, category, field.value));
  });
  const modeField = scope.querySelector('.generation-ipadapter-mode, #generation-ipadapter-mode');
  updateGenerationIpAdapterOptionExplainer(explainer, 'mode', modeField?.value || 'standard');
}
const generationSizePresetStorageKey = 'neo_studio_generation_size_presets_v1';
const generationBuiltinSizePresets = [
  { value:'builtin:sd15_square_512', label:'SD 1.5 · Square · 512 × 512', width:512, height:512, family:'SD 1.5', builtin:true },
  { value:'builtin:sd15_portrait_512x768', label:'SD 1.5 · Portrait · 512 × 768', width:512, height:768, family:'SD 1.5', builtin:true },
  { value:'builtin:sd15_landscape_768x512', label:'SD 1.5 · Landscape · 768 × 512', width:768, height:512, family:'SD 1.5', builtin:true },
  { value:'builtin:sd15_portrait_576x768', label:'SD 1.5 · Portrait · 576 × 768', width:576, height:768, family:'SD 1.5', builtin:true },
  { value:'builtin:sd15_landscape_768x576', label:'SD 1.5 · Landscape · 768 × 576', width:768, height:576, family:'SD 1.5', builtin:true },
  { value:'builtin:sd15_portrait_640x960', label:'SD 1.5 · Portrait · 640 × 960', width:640, height:960, family:'SD 1.5', builtin:true },
  { value:'builtin:sd15_landscape_960x640', label:'SD 1.5 · Landscape · 960 × 640', width:960, height:640, family:'SD 1.5', builtin:true },
  { value:'builtin:sdxl_square_1024', label:'SDXL · Square · 1024 × 1024', width:1024, height:1024, family:'SDXL', builtin:true },
  { value:'builtin:sdxl_portrait_832x1216', label:'SDXL · Portrait · 832 × 1216', width:832, height:1216, family:'SDXL', builtin:true },
  { value:'builtin:sdxl_landscape_1216x832', label:'SDXL · Landscape · 1216 × 832', width:1216, height:832, family:'SDXL', builtin:true },
  { value:'builtin:sdxl_portrait_896x1152', label:'SDXL · Portrait · 896 × 1152', width:896, height:1152, family:'SDXL', builtin:true },
  { value:'builtin:sdxl_landscape_1152x896', label:'SDXL · Landscape · 1152 × 896', width:1152, height:896, family:'SDXL', builtin:true },
  { value:'builtin:sdxl_portrait_768x1344', label:'SDXL · Portrait · 768 × 1344', width:768, height:1344, family:'SDXL', builtin:true },
  { value:'builtin:sdxl_landscape_1344x768', label:'SDXL · Landscape · 1344 × 768', width:1344, height:768, family:'SDXL', builtin:true },
  { value:'builtin:sdxl_portrait_1024x1536', label:'SDXL · Portrait · 1024 × 1536', width:1024, height:1536, family:'SDXL', builtin:true },
  { value:'builtin:sdxl_landscape_1536x1024', label:'SDXL · Landscape · 1536 × 1024', width:1536, height:1024, family:'SDXL', builtin:true },
];
let generationCatalogState = { checkpoints: [], unet: [], diffusion_models: [], clip: [], text_encoders: [], loras: [], controlnet: [], ipadapter: [], clip_vision: [], vae: [], upscalers: [], facerestore_models: [], samplers: generationFallbackSamplers.slice(), schedulers: generationFallbackSchedulers.slice(), features:{}, dynamic_thresholding:{}, res4lyf:{ installed:false, ready:false, status:'not_installed', samplers:[], schedulers:[], has_clownshark_sampler:false } };
let generationSystemStats = {};
let generationDependencyAuditState = { ok:false, issues:[], summary:{}, yaml:{ active:false, files:[], paths_by_category:{} }, checked_nodes:[], checked_models:[] };
let generationDependencyAuditCacheKey = '';
let generationDependencyAuditCacheAt = 0;
let generationLoraCompatibilityState = { family:'all', baseModelFilter:'all', compatibleEntries:[], availableBaseModels:[] };
let generationLoraRowCounter = 0;
let generationControlnetRowCounter = 0;
let generationIpAdapterRowCounter = 0;
let generationProgressSocket = null;
let generationProgressClientId = '';
let generationProgressPromptId = '';
let generationProgressStartedAt = 0;
let generationLivePreviewUrl = '';
let generationLastProgressPercent = 0;
let generationLastUsedSeed = '';
let generationPreviewActionTarget = null;
let generationLatestJobSnapshot = null;
let generationSelectedOutputSnapshot = null;
let generationActiveOutputSnapshot = null;
let generationPendingDerivedFocus = null;
const generationOutputLineageState = { entries: {}, pendingJobs: {} };
let generationDraftSaveTimer = null;
let generationDraftApplyInProgress = false;
let pendingGenerationDraft = null;
const generationRecentRunsStorageKey = 'neo_studio_generation_recent_runs_v1';
let generationRecentRuns = [];
const generationSnapshotStorageKey = 'neo_studio_generation_shell_snapshots_v1';
const generationDefaultSnapshotStorageKey = 'neo_studio_generation_shell_default_snapshot_v1';
let generationOutputSettingsLoaded = false;
let generationOutputNextIndex = 1;
let generationStyleLibrary = [];
let generationActiveStyles = [];
let generationStyleEditingName = '';
let generationStyleSearchQuery = '';
let generationMaskEditorState = { sourceImage:null, displayScale:1, exportCanvas:null, drawing:false, lastPoint:null, brushMode:'paint', displayWidth:0, displayHeight:0, zoom:1, minZoom:1, maxZoom:8, panning:false, panLast:null, spaceDown:false };
let generationSourceImageInfo = { width:0, height:0, name:'', size:0 };
let generationOutpaintPresetApplying = false;
let generationLoraLibraryState = { entries: [], currentLid:'', currentRecord:null, editMode:false, previewUrls:[], previewIndex:0, promptOptions:[], selectedPromptOptionId:'__default__', busy:false };
let generationTiLibraryState = { entries: [], currentLid:'', currentRecord:null, previewUrls:[], previewIndex:0 };
let generationTagAssistState = { caption:'', tags:[], selected: new Set(), lastImageName:'' };
let generationDetailerBoxEditorState = { image:null, imageUrl:'', imageName:'', displayWidth:0, displayHeight:0, boxes:[], activeIndex:-1, drawing:false, dragPointerId:null, startX:0, startY:0, currentX:0, currentY:0, previewSource:'manual', previewMeta:null, scopeType:'primary', scopeRowUid:'', snapshots:{}, dragMode:'', activeHandle:'', dragStartX:0, dragStartY:0, boxStart:null };
const generationImageUpscaleProfiles = {
  preserve_2x: { label:'Preserve 2×', scale:'2.0', resize_method:'lanczos', restore_assist:'off', restore_fidelity:'0.65' },
  preserve_4x: { label:'Preserve 4×', scale:'4.0', resize_method:'lanczos', restore_assist:'off', restore_fidelity:'0.65' },
  portrait_restore_2x: { label:'Portrait restore 2×', scale:'2.0', resize_method:'lanczos', restore_assist:'codeformer', restore_fidelity:'0.60' },
};
const generationUpscaleLabProfiles = {
  gentle_polish: { label:'Gentle polish', enabled:'true', mode:'latent', resize_method:'lanczos', scale:'1.25', steps:'10', denoise:'0.10', cfg:'5.0', sampler:'', scheduler:'', tiled_vae:'true', tile_size:'512', tile_overlap:'64', upscaler:'' },
  balanced_finish: { label:'Balanced finish', enabled:'true', mode:'latent', resize_method:'lanczos', scale:'1.45', steps:'12', denoise:'0.12', cfg:'5.2', sampler:'', scheduler:'', tiled_vae:'true', tile_size:'512', tile_overlap:'64', upscaler:'' },
  detail_push: { label:'Detail push', enabled:'true', mode:'image_upscale', resize_method:'lanczos', scale:'1.75', steps:'14', denoise:'0.18', cfg:'4.8', sampler:'', scheduler:'', tiled_vae:'true', tile_size:'512', tile_overlap:'64', upscaler:'' },
  bigger_finish: { label:'Bigger finish', enabled:'true', mode:'latent', resize_method:'lanczos', scale:'2.0', steps:'12', denoise:'0.12', cfg:'5.2', sampler:'', scheduler:'', tiled_vae:'true', tile_size:'640', tile_overlap:'64', upscaler:'' },
};
const generationRuntimeProfiles = {
  low_vram: {
    label:'Low VRAM',
    note:'Keep starts conservative, batch at 1, and treat redraw or SUPIR as opt-in so the backend does not get crushed.',
    hint:'Safer for tighter local memory budgets.',
  },
  mid_vram: {
    label:'Mid VRAM',
    note:'Balanced runtime defaults for most local setups. Good baseline before you push heavier finish passes.',
    hint:'Balanced local workflow.',
  },
  high_vram: {
    label:'High VRAM / Open',
    note:'Least restricted profile. Best when the backend has enough headroom for larger starts and heavier finish passes.',
    hint:'Open headroom for heavier paths.',
  },
  custom: {
    label:'Custom',
    note:'Neo stops making profile assumptions here. Use this once you already know the workflow and the backend can take it.',
    hint:'No profile assumptions.',
  },
};

const generationPromptConditioningModes = {
  raw: {
    label:'Raw',
    note:'Neo sends the prompt as written. Best when you already trust the prompt structure and weight syntax.',
  },
  soft_clamp: {
    label:'Soft clamp',
    note:'Explicit prompt weights are clamped into a safer range so heavy tags do not blow out the image as easily.',
  },
  balanced: {
    label:'Balanced',
    note:'Neo soft-clamps explicit weights and trims spacing noise for a steadier encode path.',
  },
};

const generationExperimentalModes = {
  off: {
    label:'Off',
    note:'Core generation stays on the standard path. Advanced slots stay visible for planning only.',
  },
  safe_sandbox: {
    label:'Safe sandbox',
    note:'Advanced slots are treated as isolated experiments so you can plan or test risky node workflows without pretending they are part of the baseline path.',
  },
  open_experimental: {
    label:'Open experimental',
    note:'Neo stops protecting the language around those slots and assumes you are deliberately working in experimental territory.',
  },
};

function getGenerationCatalogSourceKey(imageSession) {
  if (!imageSession || !imageSession.connected) return '';
  return [
    imageSession.profile_id || '',
    imageSession.profile_name || '',
    imageSession.base_url || '',
    imageSession.backend_type || '',
    imageSession.state || '',
    imageSession.connected ? '1' : '0',
  ].join('|');
}

function generationCheckpointLooksEmpty() {
  const el = $('generation-checkpoint');
  if (!el) return true;
  return !Array.from(el.options || []).some(opt => String(opt.value || '').trim());
}

function updateGenerationShellSummary(imageSession) {
  const connected = !!imageSession.connected;
  const label = imageSession.profile_name || 'Image Backend';
  const baseUrl = imageSession.base_url || '';
  const caps = Array.isArray(imageSession.capabilities) && imageSession.capabilities.length ? imageSession.capabilities.join(' · ') : '';
  if ($('generation-backend-summary')) $('generation-backend-summary').textContent = connected ? `${label}${baseUrl ? ` · ${baseUrl}` : ''}` : 'No image backend connected';
  if ($('generation-queue-summary')) $('generation-queue-summary').textContent = connected ? `Ready${caps ? ` · ${caps}` : ''}` : 'Connect an Image Backend first';
  if ($('generation-preview-state') && !lastGenerationJobId) $('generation-preview-state').textContent = connected
    ? 'Image backend connected. Pick a checkpoint, then queue from Neo Studio.'
    : 'No generation job has been queued from Neo Studio yet. Connect ComfyUI, pick a checkpoint, and queue from here.';
  if (!generationLatestJobSnapshot) syncGenerationActionZoneFromShell();
  renderGenerationRuntimeProfileAndCapabilities();
  renderGenerationPromptConditioning();
  renderGenerationExperimentalMode();
  if (typeof renderGenerationDynamicThresholding === 'function') renderGenerationDynamicThresholding();
}

function generationActionModeLabel(mode='txt2img') {
  const value = String(mode || '').trim().toLowerCase();
  if (!value) return 'txt2img';
  if (value === 'img2img') return 'img2img';
  if (value === 'inpaint') return 'inpaint';
  if (value === 'outpaint') return 'outpaint';
  return value;
}

function generationActionToneFromState(state='idle') {
  const value = String(state || '').trim().toLowerCase();
  if (['completed', 'success', 'ready'].includes(value)) return 'success';
  if (['running', 'queued', 'processing', 'executing', 'connecting', 'monitoring'].includes(value)) return 'running';
  if (['paused', 'cancelled', 'interrupted', 'stopped'].includes(value)) return 'paused';
  if (['error', 'failed', 'offline'].includes(value)) return 'error';
  if (['detail', 'mode'].includes(value)) return 'detail';
  return 'idle';
}

function setGenerationActionChip(id, text, tone='idle') {
  const el = $(id);
  if (!el) return;
  el.textContent = text || '—';
  el.className = `generation-action-chip is-${generationActionToneFromState(tone)}`;
}

function syncGenerationActionZoneMeta({ stateText='', stateTone='idle', modeText='', queueText='', jobText='', payloadText='', backendText='' } = {}) {
  if ($('generation-action-status-chip')) setGenerationActionChip('generation-action-status-chip', stateText || 'Idle', stateTone || 'idle');
  if ($('generation-action-mode-chip')) setGenerationActionChip('generation-action-mode-chip', modeText || generationActionModeLabel($('generation-workflow-type')?.value || 'txt2img'), 'detail');
  if ($('generation-action-queue-meta')) $('generation-action-queue-meta').textContent = queueText || $('generation-queue-summary')?.textContent || '—';
  if ($('generation-action-job-meta')) $('generation-action-job-meta').textContent = jobText || $('generation-last-job-summary')?.textContent || 'No job yet';
  if ($('generation-action-payload-meta')) $('generation-action-payload-meta').textContent = payloadText || $('generation-payload-summary')?.textContent || 'Not queued yet';
  if ($('generation-action-backend-badge')) $('generation-action-backend-badge').textContent = backendText || (($('generation-backend-summary')?.textContent || '').includes('No image backend connected') ? 'Backend offline' : 'Backend live');
}

function syncGenerationActionZoneFromShell() {
  const backendSummary = $('generation-backend-summary')?.textContent || 'No image backend connected';
  const connected = !/no image backend connected/i.test(backendSummary);
  const latestJob = ($('generation-last-job-summary')?.textContent || '').trim();
  const stateText = latestJob && !/^no job yet$/i.test(latestJob) ? 'Monitoring' : (connected ? 'Ready' : 'Offline');
  const stateTone = latestJob && !/^no job yet$/i.test(latestJob) ? 'running' : (connected ? 'success' : 'error');
  syncGenerationActionZoneMeta({
    stateText,
    stateTone,
    modeText: generationActionModeLabel($('generation-workflow-type')?.value || 'txt2img'),
    queueText: $('generation-queue-summary')?.textContent || (connected ? 'Ready' : 'Connect an Image Backend first'),
    jobText: latestJob || 'No job yet',
    payloadText: $('generation-payload-summary')?.textContent || 'Not queued yet',
    backendText: connected ? 'Backend live' : 'Backend offline',
  });
}

function generationSelectItemValue(item) {
  if (item && typeof item === 'object') return String(item.value ?? item.id ?? item.name ?? '');
  return String(item ?? '');
}

function generationSelectItemLabel(item) {
  if (item && typeof item === 'object') return String(item.label ?? item.name ?? item.value ?? item.id ?? '');
  return String(item ?? '');
}

function detectGenerationCheckpointFamily() {
  const explicitFamily = trim($('generation-family')?.value || "").toLowerCase();
  if (explicitFamily === 'flux') return 'flux';
  if (explicitFamily === 'qwen_image_edit') return 'qwen_image';
  const modelSource = trim($('generation-model-source')?.value || "checkpoint").toLowerCase();
  const ggufType = trim($('generation-gguf-clip-type')?.value || "").toLowerCase();
  if (modelSource === 'gguf') {
    if (ggufType === 'qwen_image') return 'qwen_image';
    if (ggufType === 'flux') return 'flux';
  }
  const select = $('generation-checkpoint');
  const raw = `${trim(select?.value || '')} ${trim(select?.selectedOptions?.[0]?.textContent || '')}`.toLowerCase();
  if (!raw) return 'all';
  if (raw.includes('flux')) return 'flux';
  if (raw.includes('qwen') || raw.includes('qwen image') || raw.includes('qwen-image') || raw.includes('qwen2.5-vl') || raw.includes('qwen vl')) return 'qwen_image';
  if (raw.includes('sdxl') || /(^|[^a-z])xl([^a-z]|$)/.test(raw)) return 'sdxl';
  if (raw.includes('1.5') || raw.includes('sd15') || raw.includes('sd 1.5') || raw.includes('v1-5') || raw.includes('1_5')) return 'sd1.5';
  return 'all';
}

function resolveGenerationLoraBaseModelFilter(baseModels=[], family='all') {
  const rows = Array.isArray(baseModels) ? baseModels.filter(Boolean) : [];
  if (!rows.length || !family || family === 'all') return 'all';
  const findMatch = predicates => rows.find(value => {
    const lower = String(value || '').toLowerCase();
    return predicates.some(fn => fn(lower));
  });
  if (family === 'flux') return findMatch([v => v.includes('flux')]) || 'all';
  if (family === 'qwen_image') {
    return findMatch([
      v => v.includes('qwen image'),
      v => v.includes('qwen-image'),
      v => v.includes('qwen image edit'),
      v => v.includes('qwen-image-edit'),
      v => v.includes('qwen2.5-vl'),
      v => v.includes('qwen 2.5 vl'),
      v => v.includes('qwen vl'),
      v => v == 'qwen',
      v => v.startsWith('qwen'),
    ]) || 'all';
  }
  if (family === 'sdxl') return findMatch([v => v.includes('sdxl'), v => /(^|[^a-z])xl([^a-z]|$)/.test(v)]) || 'all';
  if (family === 'sd1.5') return findMatch([v => v.includes('sd 1.5'), v => v.includes('sd1.5'), v => v.includes('1.5'), v => v.includes('v1-5')]) || 'all';
  return 'all';
}

function generationLoraStrictEntryMatch(entries, rawName='') {
  const rawList = Array.isArray(rawName) ? rawName : [rawName];
  const names = [];
  rawList.forEach(value => {
    const raw = trim(value || '');
    if (!raw) return;
    const variants = [raw, raw.split(/[\/]/).pop(), raw.replace(/\.[a-z0-9]+$/i, '')].filter(Boolean);
    variants.forEach(item => {
      const lower = trim(item || '').toLowerCase();
      if (lower && !names.includes(lower)) names.push(lower);
    });
  });
  if (!names.length) return false;
  return (entries || []).some(item => {
    const label = trim(item?.label || '').toLowerCase();
    const id = trim(item?.id || '').toLowerCase();
    const rel = trim(item?.rel || '').toLowerCase();
    const name = trim(item?.name || '').toLowerCase();
    return names.some(nameValue => {
      const base = nameValue.replace(/\.[a-z0-9]+$/i, '');
      return [label, id, rel, name].some(value => value && (value === nameValue || (!!base && value.includes(base))));
    });
  });
}

function generationLoraCompatibilityText(entryOrValue) {
  if (!entryOrValue) return '';
  if (typeof entryOrValue === 'string') return trim(entryOrValue).toLowerCase();
  return [
    entryOrValue.label,
    entryOrValue.id,
    entryOrValue.name,
    entryOrValue.rel,
    entryOrValue.category,
    entryOrValue.base_model,
    entryOrValue.style_category,
    entryOrValue.provider_label,
    entryOrValue.notes,
  ].map(v => trim(v || '').toLowerCase()).filter(Boolean).join(' ');
}

function generationLoraFamilySignals(raw='') {
  const text = trim(raw || '').toLowerCase();
  const has = (...tokens) => tokens.some(token => text.includes(token));
  const rx = regex => regex.test(text);
  return {
    qwen: has('qwen image edit', 'qwen-image-edit', 'qwen image', 'qwen-image', 'qwen2.5-vl', 'qwen 2.5 vl', 'qwen vl') || rx(/(^|[^a-z])qwen([^a-z]|$)/),
    flux: has('flux klein', 'flux-klein', 'flux.1-klein', 'flux1 klein', 'flux') || rx(/(^|[^a-z])flux([^a-z]|$)/),
    sdxl: has('sdxl', 'stable diffusion xl', 'pony', 'illustrious') || rx(/(^|[^a-z])xl([^a-z]|$)/),
    sd15: has('sd 1.5', 'sd1.5', 'stable diffusion 1.5', 'v1-5', '1_5', '1.5'),
    sd2: has('sd 2', 'sd2', 'stable diffusion 2', '2.1', '2_1'),
  };
}

function generationLoraFamilyCompatibility(entry, family='all') {
  const text = generationLoraCompatibilityText(entry);
  const signals = generationLoraFamilySignals(text);
  const incompatibleLegacy = signals.sdxl || signals.sd15 || signals.sd2;
  if (!family || family === 'all') return { visible:true, reason:'' };
  if (family === 'qwen_image') {
    if (signals.qwen) return { visible:true, reason:'qwen' };
    if (signals.flux) return { visible:true, reason:'flux-compatible' };
    if (incompatibleLegacy) return { visible:false, reason:'clearly-built-for-other-family' };
    return { visible:true, reason:'unknown-kept-visible' };
  }
  if (family === 'flux') {
    if (signals.flux) return { visible:true, reason:'flux' };
    if (signals.qwen) return { visible:true, reason:'qwen-or-flux-cross-compatible' };
    if (incompatibleLegacy) return { visible:false, reason:'clearly-built-for-other-family' };
    return { visible:true, reason:'unknown-kept-visible' };
  }
  if (family === 'sdxl') {
    if (signals.sdxl) return { visible:true, reason:'sdxl' };
    if (signals.qwen || signals.flux || signals.sd15 || signals.sd2) return { visible:false, reason:'clearly-built-for-other-family' };
    return { visible:true, reason:'unknown-kept-visible' };
  }
  if (family === 'sd1.5') {
    if (signals.sd15) return { visible:true, reason:'sd15' };
    if (signals.qwen || signals.flux || signals.sdxl || signals.sd2) return { visible:false, reason:'clearly-built-for-other-family' };
    return { visible:true, reason:'unknown-kept-visible' };
  }
  return { visible:true, reason:'' };
}

function generationFindLoraCompatibilityEntry(rawName='') {
  const entries = generationLoraCompatibilityState.allEntries || generationLoraCompatibilityState.compatibleEntries || [];
  const rawList = Array.isArray(rawName) ? rawName : [rawName];
  return (entries || []).find(item => generationLoraStrictEntryMatch([item], rawList)) || null;
}

function getGenerationCompatibleLoraOptions() {
  const family = generationLoraCompatibilityState.family || 'all';
  return (generationCatalogState.loras || []).filter(item => {
    const match = generationFindLoraCompatibilityEntry([generationSelectItemValue(item), generationSelectItemLabel(item)]);
    if (!match) return true;
    return generationLoraFamilyCompatibility(match, family).visible !== false;
  });
}

function setGenerationCompatibleLoraOptionsForElement(selectEl, placeholder='None') {
  if (!selectEl) return;
  const compatible = getGenerationCompatibleLoraOptions();
  const current = trim(selectEl.value || '');
  let items = Array.isArray(compatible) ? compatible.slice() : [];
  if (current && !items.some(item => generationSelectItemValue(item) === current)) {
    items.unshift({ value: current, label: `${current} · hidden by compatibility guard` });
  }
  setSelectOptionsForElement(selectEl, items, placeholder);
}

async function ensureGenerationLoraCompatibilityState(force=false) {
  const family = detectGenerationCheckpointFamily();
  if (!force && generationLoraCompatibilityState.family === family && Array.isArray(generationLoraCompatibilityState.allEntries) && generationLoraCompatibilityState.allEntries.length) {
    return generationLoraCompatibilityState;
  }
  try {
    const allData = await safeFetchJson('/api/neo-library/lora-browser?kind=lora&query=&category=all&style_category=all&base_model=all', { cache:'no-store' });
    const availableBaseModels = Array.isArray(allData.base_models) ? allData.base_models : [];
    const allEntries = Array.isArray(allData.entries) ? allData.entries : [];
    const compatibleEntries = allEntries.filter(item => generationLoraFamilyCompatibility(item, family).visible !== false);
    generationLoraCompatibilityState = { family, baseModelFilter:'all', compatibleEntries, allEntries, availableBaseModels };
  } catch (_) {
    generationLoraCompatibilityState = { family, baseModelFilter:'all', compatibleEntries:[], allEntries:[], availableBaseModels:[] };
  }
  return generationLoraCompatibilityState;
}

async function applyGenerationLoraCompatibilityFilter(options={}) {
  const refreshLibrary = options.refreshLibrary !== false;
  await ensureGenerationLoraCompatibilityState(!!options.force);
  refreshGenerationDynamicOptions();
  if (refreshLibrary) {
    await refreshGenerationLoraLibraryBrowser({ keepSelection:true });
    await refreshGenerationTiLibraryBrowser({ keepSelection:true });
  }
  const familyLabel = generationLoraCompatibilityState.family === 'sd1.5' ? 'SD 1.5' : (generationLoraCompatibilityState.family === 'qwen_image' ? 'Qwen Image' : (generationLoraCompatibilityState.family || 'all').toUpperCase());
  const hiddenCount = Math.max(0, (generationLoraCompatibilityState.allEntries || []).length - (generationLoraCompatibilityState.compatibleEntries || []).length);
  setStatus('generation-lora-library-status', hiddenCount > 0 ? `${familyLabel} compatibility guard active · hiding ${hiddenCount} clearly incompatible LoRA(s)` : `${familyLabel} compatibility guard active · only obvious mismatches are hidden`, '');
}

function loadGenerationCustomSizePresets() {
  try {
    const raw = localStorage.getItem(generationSizePresetStorageKey);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(item => Number(item?.width || 0) > 0 && Number(item?.height || 0) > 0) : [];
  } catch (_) {
    return [];
  }
}

function saveGenerationCustomSizePresets(items) {
  try {
    localStorage.setItem(generationSizePresetStorageKey, JSON.stringify(Array.isArray(items) ? items : []));
  } catch (_) {}
}

function getGenerationSizePresets() {
  return [...generationBuiltinSizePresets, ...loadGenerationCustomSizePresets()];
}

function makeGenerationCustomPreset(width, height) {
  const w = Math.max(64, Number(width || 0) || 0);
  const h = Math.max(64, Number(height || 0) || 0);
  return {
    value: `custom:${w}x${h}`,
    label: `Custom · ${w} × ${h}`,
    width: w,
    height: h,
    family: 'Custom',
    builtin: false,
  };
}

function findGenerationSizePresetByValue(value='') {
  const target = String(value || '').trim();
  if (!target || target === 'custom') return null;
  return getGenerationSizePresets().find(item => String(item.value || '') === target) || null;
}

function findGenerationSizePresetByDimensions(width, height) {
  const w = Number(width || 0) || 0;
  const h = Number(height || 0) || 0;
  if (!(w > 0 && h > 0)) return null;
  return getGenerationSizePresets().find(item => Number(item.width || 0) === w && Number(item.height || 0) === h) || null;
}

function updateGenerationSizePresetNote(message='') {
  const note = $('generation-size-preset-note');
  if (!note) return;
  note.textContent = message || 'Pick a built-in SD 1.5 or SDXL friendly size, or save the current size as a custom preset.';
}

function populateGenerationSizePresetSelect(selectedValue='custom') {
  const select = $('generation-size-preset');
  if (!select) return;
  const current = String(selectedValue || select.value || 'custom');
  const presets = getGenerationSizePresets();
  select.innerHTML = '';
  const customOpt = document.createElement('option');
  customOpt.value = 'custom';
  customOpt.textContent = 'Custom size';
  select.appendChild(customOpt);
  presets.forEach(item => {
    const opt = document.createElement('option');
    opt.value = String(item.value || '');
    opt.textContent = generationSelectItemLabel(item);
    select.appendChild(opt);
  });
  select.value = presets.some(item => String(item.value || '') === current) ? current : 'custom';
}

function syncGenerationSizePresetSelectionFromInputs() {
  populateGenerationSizePresetSelect($('generation-size-preset')?.value || 'custom');
  const width = Number($('generation-width')?.value || 0) || 0;
  const height = Number($('generation-height')?.value || 0) || 0;
  const matched = findGenerationSizePresetByDimensions(width, height);
  const select = $('generation-size-preset');
  if (select) select.value = matched ? String(matched.value || 'custom') : 'custom';
  if (matched) updateGenerationSizePresetNote(`${matched.label} · ${matched.builtin ? 'built-in preset' : 'saved custom preset'}`);
  else if (width > 0 && height > 0) updateGenerationSizePresetNote(`Custom size · ${width} × ${height}`);
  else updateGenerationSizePresetNote();
}

function applyGenerationSizePreset(value, { quiet=false, skipSave=false } = {}) {
  const preset = findGenerationSizePresetByValue(value);
  if (!preset) {
    syncGenerationSizePresetSelectionFromInputs();
    return false;
  }
  if ($('generation-width')) $('generation-width').value = String(preset.width);
  if ($('generation-height')) $('generation-height').value = String(preset.height);
  syncGenerationSizePresetSelectionFromInputs();
  if (!skipSave) scheduleGenerationDraftSave();
  if (!quiet) setStatus('generation-status', `Size preset applied: ${preset.label}.`);
  return true;
}

function addCurrentGenerationSizePreset() {
  const width = Number($('generation-width')?.value || 0) || 0;
  const height = Number($('generation-height')?.value || 0) || 0;
  if (!(width >= 64 && height >= 64)) {
    setStatus('generation-status', 'Enter a valid width and height first.', 'warn');
    return;
  }
  const builtinMatch = generationBuiltinSizePresets.find(item => Number(item.width || 0) === width && Number(item.height || 0) === height);
  if (builtinMatch) {
    populateGenerationSizePresetSelect(String(builtinMatch.value || 'custom'));
    if ($('generation-size-preset')) $('generation-size-preset').value = String(builtinMatch.value || 'custom');
    updateGenerationSizePresetNote(`${builtinMatch.label} · already included as a built-in preset.`);
    setStatus('generation-status', 'That size already exists in the built-in preset list.');
    return;
  }
  const customPresets = loadGenerationCustomSizePresets();
  const exists = customPresets.find(item => Number(item.width || 0) === width && Number(item.height || 0) === height);
  const preset = exists || makeGenerationCustomPreset(width, height);
  if (!exists) {
    customPresets.unshift(preset);
    saveGenerationCustomSizePresets(customPresets.slice(0, 24));
  }
  populateGenerationSizePresetSelect(String(preset.value || 'custom'));
  if ($('generation-size-preset')) $('generation-size-preset').value = String(preset.value || 'custom');
  updateGenerationSizePresetNote(`${preset.label} · saved to your local preset list.`);
  scheduleGenerationDraftSave();
  setStatus('generation-status', `Saved ${width} × ${height} as a reusable size preset.`);
}

function swapGenerationDimensions() {
  const widthEl = $('generation-width');
  const heightEl = $('generation-height');
  if (!widthEl || !heightEl) return;
  const currentWidth = widthEl.value;
  widthEl.value = heightEl.value;
  heightEl.value = currentWidth;
  syncGenerationSizePresetSelectionFromInputs();
  scheduleGenerationDraftSave();
}

function isGenerationUnitEnabledFromCheckbox(checkbox) {
  return !(checkbox instanceof HTMLInputElement) || checkbox.checked !== false;
}

function toggleGenerationUnitDisabledState(card, enabled) {
  if (!card) return;
  card.classList.toggle('is-disabled', !enabled);
}

function moveGenerationUnitRow(row, direction=1) {
  if (!row?.parentElement) return;
  if (direction < 0 && row.previousElementSibling) row.parentElement.insertBefore(row, row.previousElementSibling);
  else if (direction > 0 && row.nextElementSibling) row.parentElement.insertBefore(row.nextElementSibling, row);
  updateGenerationUnitIndices();
  scheduleGenerationDraftSave();
}

function updateGenerationUnitIndices() {
  const loraRows = [document.querySelector('.generation-lora-primary-row'), ...Array.from(document.querySelectorAll('#generation-lora-extra-list .generation-lora-row'))].filter(Boolean);
  loraRows.forEach((row, index) => {
    const badge = row.querySelector('.generation-unit-index');
    if (badge) badge.textContent = String(index + 1).padStart(2, '0');
  });
  const controlRows = [document.querySelector('.generation-unit-card-controlnet[data-primary="true"]'), ...Array.from(document.querySelectorAll('#generation-controlnet-extra-list .generation-controlnet-row'))].filter(Boolean);
  controlRows.forEach((row, index) => {
    const badge = row.querySelector('.generation-unit-index');
    if (badge) badge.textContent = String(index + 1).padStart(2, '0');
  });
  const ipadapterRows = [document.querySelector('.generation-unit-card-ipadapter[data-primary="true"]'), ...Array.from(document.querySelectorAll('#generation-ipadapter-extra-list .generation-ipadapter-row'))].filter(Boolean);
  ipadapterRows.forEach((row, index) => {
    const badge = row.querySelector('.generation-unit-index');
    if (badge) badge.textContent = String(index + 1).padStart(2, '0');
  });
  const detailerRows = Array.from(document.querySelectorAll('#generation-detailer-extra-list .generation-detailer-row')).filter(Boolean);
  detailerRows.forEach((row, index) => {
    const badge = row.querySelector('.generation-unit-index');
    if (badge) badge.textContent = String(index + 1).padStart(2, '0');
  });
  updateGenerationDetailerEditorScopeLabel();
}

function updateGenerationPreviewImage(input, preview, empty) {
  if (!preview || !empty) return;
  const file = input?.files?.[0] || null;
  const oldUrl = preview.dataset.objectUrl || '';
  if (oldUrl) {
    try { URL.revokeObjectURL(oldUrl); } catch (_) {}
    preview.dataset.objectUrl = '';
  }
  if (!file) {
    preview.removeAttribute('src');
    preview.classList.add('hidden');
    preview.closest('.generation-unit-preview-card')?.classList.remove('is-has-image');
    empty.classList.remove('hidden');
    return;
  }
  const url = URL.createObjectURL(file);
  preview.src = url;
  preview.dataset.objectUrl = url;
  preview.classList.remove('hidden');
  preview.closest('.generation-unit-preview-card')?.classList.add('is-has-image');
  empty.classList.add('hidden');
}

function updatePrimaryGenerationLoraSummary() {
  const enabled = isGenerationUnitEnabledFromCheckbox($('generation-lora-enabled'));
  const name = trim($('generation-lora-name')?.value || '');
  const strength = Number($('generation-lora-strength')?.value || 0.8);
  const summary = $('generation-lora-primary-summary');
  toggleGenerationUnitDisabledState(document.querySelector('.generation-lora-primary-row'), enabled);
  if (!summary) return;
  if (!enabled) {
    summary.innerHTML = '<strong>Disabled.</strong> This primary LoRA slot will be skipped.';
    return;
  }
  if (!name) {
    summary.innerHTML = 'Add LoRAs from the library below.';
    return;
  }
  summary.innerHTML = `<span class="generation-chip">LoRA</span><strong>${escapeHtml(name)}</strong> · strength ${Number.isFinite(strength) ? strength.toFixed(2) : '0.80'}`;
}

function updateGenerationLoraRowSummary(row) {
  if (!row) return;
  const enabled = isGenerationUnitEnabledFromCheckbox(row.querySelector('.generation-unit-enabled'));
  const name = trim(row.querySelector('.generation-lora-name')?.value || '');
  const strength = Number(row.querySelector('.generation-lora-strength')?.value || 0.8);
  const target = normalizeGenerationPassTarget(row.querySelector('.generation-lora-target')?.value || 'both');
  const applyTo = (typeof normalizeGenerationLoraApplyTo === 'function') ? normalizeGenerationLoraApplyTo(row.querySelector('.generation-lora-apply-to')?.value || 'global') : 'global';
  const summary = row.querySelector('.generation-unit-summary');
  toggleGenerationUnitDisabledState(row, enabled);
  syncGenerationDetailerRowManualUi(row);
  if (!summary) return;
  if (!enabled) {
    summary.innerHTML = '<strong>Disabled.</strong> This LoRA row stays in the stack but will not be sent.';
    return;
  }
  if (!name) {
    summary.innerHTML = 'Pick a LoRA for this stack slot.';
    return;
  }
  const applyLabel = (typeof generationLoraApplyToLabel === 'function') ? generationLoraApplyToLabel(applyTo) : applyTo;
  summary.innerHTML = `<span class="generation-chip">LoRA</span><strong>${escapeHtml(name)}</strong> · strength ${Number.isFinite(strength) ? strength.toFixed(2) : '0.80'} · ${escapeHtml(applyLabel)} · ${escapeHtml(generationPassTargetLabel(target))}`;
}

function generationLoraMetaFields() {
  return [
    'generation-lora-library-base-model',
    'generation-lora-library-style-category',
    'generation-lora-library-strength',
    'generation-lora-library-min-strength',
    'generation-lora-library-max-strength',
    'generation-lora-library-civitai-url',
    'generation-lora-library-triggers',
    'generation-lora-library-keywords',
    'generation-lora-library-example',
    'generation-lora-library-prompt-option-name',
  ];
}

function appendTextToGenerationPromptField(fieldId, addText='', separator=', ') {
  const el = $(fieldId);
  const add = trim(addText || '');
  if (!el || !add) return false;
  const current = trim(el.value || '');
  if (!current) {
    el.value = add;
  } else {
    const existing = current.toLowerCase();
    if (existing.includes(add.toLowerCase())) return false;
    el.value = `${current}${separator}${add}`;
  }
  el.dispatchEvent(new Event('input', { bubbles:true }));
  el.dispatchEvent(new Event('change', { bubbles:true }));
  return true;
}

function promptContainsGenerationToken(token='') {
  const target = trim(token || '').toLowerCase();
  const prompt = trim($('generation-positive')?.value || '').toLowerCase();
  if (!target || !prompt) return false;
  return prompt.includes(target);
}

function setGenerationLoraLibraryBusy(isBusy=false, label='Working…', note='Please wait') {
  generationLoraLibraryState.busy = !!isBusy;
  const shell = $('generation-lora-library-progress-shell');
  if (shell) shell.classList.toggle('hidden', !isBusy);
  if ($('generation-lora-library-progress-label')) $('generation-lora-library-progress-label').textContent = label || 'Working…';
  if ($('generation-lora-library-progress-note')) $('generation-lora-library-progress-note').textContent = note || 'Please wait';
  const ids = [
    'btn-generation-lora-library-pull',
    'btn-generation-lora-library-save',
    'btn-generation-lora-library-edit',
    'btn-generation-lora-library-add-to-workflow',
    'btn-generation-lora-library-scan',
    'btn-generation-lora-library-refresh',
    'btn-generation-lora-library-prompt-save-option',
    'btn-generation-lora-library-prompt-update-option',
    'btn-generation-lora-library-prompt-delete-option',
  ];
  ids.forEach(id => {
    const el = $(id);
    if (!el) return;
    if (isBusy) el.setAttribute('disabled', 'disabled');
    else el.removeAttribute('disabled');
  });
  syncGenerationLoraPromptOptionButtons();
  setGenerationLoraLibraryEditMode(generationLoraLibraryState.editMode);
}

function setGenerationLoraLibraryEditMode(enabled=false) {
  generationLoraLibraryState.editMode = !!enabled;
  const editing = generationLoraLibraryState.editMode;
  $('generation-lora-library-shell')?.classList.toggle('is-editing', editing);
  generationLoraMetaFields().forEach(id => {
    const el = $(id);
    if (!el) return;
    if (editing) el.removeAttribute('readonly');
    else el.setAttribute('readonly', 'readonly');
  });
  const hasLid = !!trim(generationLoraLibraryState.currentLid || '');
  if ($('btn-generation-lora-library-save')) $('btn-generation-lora-library-save').disabled = generationLoraLibraryState.busy || !(editing && hasLid);
  if ($('btn-generation-lora-library-pull')) $('btn-generation-lora-library-pull').disabled = generationLoraLibraryState.busy || !(editing && hasLid);
  if ($('btn-generation-lora-library-edit')) $('btn-generation-lora-library-edit').classList.toggle('is-active', editing);
  syncGenerationLoraPromptOptionButtons();
  renderGenerationLoraMetaChips();
}

function generationLoraCsv(fieldId) {
  return String($(fieldId)?.value || '').split(',').map(v => trim(v)).filter(Boolean);
}

function renderGenerationLoraChipSet(wrapId, items, kind='keyword') {
  const wrap = $(wrapId);
  if (!wrap) return;
  wrap.innerHTML = '';
  const rows = (items || []).filter(Boolean);
  if (!rows.length) {
    wrap.innerHTML = `<span class="mini-note">No ${kind === 'trigger' ? 'trigger words' : 'keywords'} saved for this LoRA yet.</span>`;
    return;
  }
  rows.forEach(item => {
    const chip = document.createElement('button');
    const sent = promptContainsGenerationToken(item);
    chip.type = 'button';
    chip.className = `generation-lora-chip${kind === 'trigger' ? ' is-trigger' : ''}${sent ? ' is-sent' : ''}`;
    chip.innerHTML = `${sent ? '<span class="generation-lora-chip-mark">✓</span>' : ''}<span>${escapeHtml(item)}</span>`;
    const disabled = generationLoraLibraryState.editMode || generationLoraLibraryState.busy;
    chip.disabled = disabled;
    if (disabled) chip.classList.add('is-disabled');
    chip.title = disabled
      ? 'Chip sending is disabled while edit mode is active.'
      : (sent ? `${item} is already in the main prompt.` : `Append ${item} to the main prompt`);
    chip.addEventListener('click', () => {
      if (generationLoraLibraryState.editMode || generationLoraLibraryState.busy) return;
      const added = appendTextToGenerationPromptField('generation-positive', item, ', ');
      renderGenerationLoraMetaChips();
      setStatus('generation-lora-library-status', added ? `Added ${kind}: ${item}` : `${item} is already in the main prompt.`, added ? 'success' : 'warn');
    });
    wrap.appendChild(chip);
  });
}

function renderGenerationLoraMetaChips() {
  renderGenerationLoraChipSet('generation-lora-library-trigger-chips', generationLoraCsv('generation-lora-library-triggers'), 'trigger');
  renderGenerationLoraChipSet('generation-lora-library-keyword-chips', generationLoraCsv('generation-lora-library-keywords'), 'keyword');
}

function setGenerationLoraPreviewIndex(index=0) {
  const previews = Array.isArray(generationLoraLibraryState.previewUrls) ? generationLoraLibraryState.previewUrls : [];
  const img = $('generation-lora-library-preview');
  const button = $('btn-generation-lora-library-preview');
  const count = $('generation-lora-library-preview-count');
  const prevBtn = $('btn-generation-lora-library-preview-prev');
  const nextBtn = $('btn-generation-lora-library-preview-next');
  if (!previews.length) {
    generationLoraLibraryState.previewIndex = 0;
    if (img) img.removeAttribute('src');
    button?.classList.remove('is-has-image');
    if (count) count.textContent = '0 / 0';
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    return;
  }
  const safeIndex = Math.max(0, Math.min(Number(index || 0) || 0, previews.length - 1));
  generationLoraLibraryState.previewIndex = safeIndex;
  const current = previews[safeIndex] || {};
  const src = current.url || '';
  if (img) {
    if (src) img.src = src;
    else img.removeAttribute('src');
  }
  button?.classList.toggle('is-has-image', !!src);
  if (count) count.textContent = `${safeIndex + 1} / ${previews.length}`;
  if (prevBtn) prevBtn.disabled = previews.length <= 1;
  if (nextBtn) nextBtn.disabled = previews.length <= 1;
}

function shiftGenerationLoraPreview(delta=1) {
  const previews = Array.isArray(generationLoraLibraryState.previewUrls) ? generationLoraLibraryState.previewUrls : [];
  if (!previews.length) return;
  const nextIndex = (generationLoraLibraryState.previewIndex + delta + previews.length) % previews.length;
  setGenerationLoraPreviewIndex(nextIndex);
}

function populateGenerationLoraPromptOptionSelect(selected='__default__') {
  const select = $('generation-lora-library-prompt-option-select');
  if (!select) return;
  select.innerHTML = '';
  const defaultOpt = document.createElement('option');
  defaultOpt.value = '__default__';
  defaultOpt.textContent = 'Default sample prompt';
  select.appendChild(defaultOpt);
  (generationLoraLibraryState.promptOptions || []).forEach(opt => {
    const node = document.createElement('option');
    node.value = String(opt.id || '');
    node.textContent = String(opt.name || 'Variant');
    select.appendChild(node);
  });
  select.value = selected || '__default__';
  generationLoraLibraryState.selectedPromptOptionId = select.value || '__default__';
}

function syncGenerationLoraPromptOptionButtons() {
  const edit = generationLoraLibraryState.editMode && !generationLoraLibraryState.busy;
  const selectedId = trim($('generation-lora-library-prompt-option-select')?.value || generationLoraLibraryState.selectedPromptOptionId || '__default__') || '__default__';
  const hasVariant = selectedId !== '__default__' && !!(generationLoraLibraryState.promptOptions || []).find(opt => String(opt.id || '') === selectedId);
  if ($('btn-generation-lora-library-prompt-save-option')) $('btn-generation-lora-library-prompt-save-option').disabled = !edit;
  if ($('btn-generation-lora-library-prompt-update-option')) $('btn-generation-lora-library-prompt-update-option').disabled = !(edit && hasVariant);
  if ($('btn-generation-lora-library-prompt-delete-option')) $('btn-generation-lora-library-prompt-delete-option').disabled = !(edit && hasVariant);
}

function loadSelectedGenerationLoraPromptOption() {
  const selectedId = trim($('generation-lora-library-prompt-option-select')?.value || '__default__') || '__default__';
  generationLoraLibraryState.selectedPromptOptionId = selectedId;
  if (selectedId === '__default__') {
    if ($('generation-lora-library-prompt-option-name')) $('generation-lora-library-prompt-option-name').value = 'Default sample';
    syncGenerationLoraPromptOptionButtons();
    return;
  }
  const option = (generationLoraLibraryState.promptOptions || []).find(opt => String(opt.id || '') === selectedId) || null;
  if (!option) return;
  if ($('generation-lora-library-prompt-option-name')) $('generation-lora-library-prompt-option-name').value = option.name || '';
  if ($('generation-lora-library-example')) $('generation-lora-library-example').value = option.text || '';
  syncGenerationLoraPromptOptionButtons();
}

function saveGenerationLoraPromptOption(update=false) {
  if (!generationLoraLibraryState.editMode) return setStatus('generation-lora-library-status', 'Enable edit mode first to change prompt options.', 'warn');
  const name = trim($('generation-lora-library-prompt-option-name')?.value || '');
  const promptText = trim($('generation-lora-library-example')?.value || '');
  if (!name) return setStatus('generation-lora-library-status', 'Give the prompt option a name first.', 'warn');
  if (!promptText) return setStatus('generation-lora-library-status', 'The sample prompt is empty.', 'warn');
  const selectedId = trim($('generation-lora-library-prompt-option-select')?.value || generationLoraLibraryState.selectedPromptOptionId || '__default__') || '__default__';
  const options = Array.isArray(generationLoraLibraryState.promptOptions) ? generationLoraLibraryState.promptOptions.slice() : [];
  if (update && selectedId !== '__default__') {
    const index = options.findIndex(opt => String(opt.id || '') === selectedId);
    if (index >= 0) {
      options[index] = { ...options[index], name, text: promptText };
      generationLoraLibraryState.promptOptions = options;
      populateGenerationLoraPromptOptionSelect(selectedId);
      syncGenerationLoraPromptOptionButtons();
      return setStatus('generation-lora-library-status', 'Prompt option updated.', 'success');
    }
  }
  const nextId = `variant_${Date.now()}`;
  options.push({ id: nextId, name, text: promptText, source: 'manual' });
  generationLoraLibraryState.promptOptions = options;
  populateGenerationLoraPromptOptionSelect(nextId);
  syncGenerationLoraPromptOptionButtons();
  setStatus('generation-lora-library-status', 'Prompt option saved.', 'success');
}

function deleteSelectedGenerationLoraPromptOption() {
  if (!generationLoraLibraryState.editMode) return setStatus('generation-lora-library-status', 'Enable edit mode first to delete prompt options.', 'warn');
  const selectedId = trim($('generation-lora-library-prompt-option-select')?.value || '__default__') || '__default__';
  if (selectedId === '__default__') return setStatus('generation-lora-library-status', 'Default sample prompt cannot be deleted.', 'warn');
  generationLoraLibraryState.promptOptions = (generationLoraLibraryState.promptOptions || []).filter(opt => String(opt.id || '') !== selectedId);
  populateGenerationLoraPromptOptionSelect('__default__');
  if ($('generation-lora-library-prompt-option-name')) $('generation-lora-library-prompt-option-name').value = 'Default sample';
  syncGenerationLoraPromptOptionButtons();
  setStatus('generation-lora-library-status', 'Prompt option deleted.', 'success');
}

function clearGenerationLoraLibraryDetails(message='Pick a scanned LoRA to inspect its saved metadata.') {
  generationLoraLibraryState.currentLid = '';
  generationLoraLibraryState.currentRecord = null;
  generationLoraLibraryState.previewUrls = [];
  generationLoraLibraryState.previewIndex = 0;
  generationLoraLibraryState.promptOptions = [];
  generationLoraLibraryState.selectedPromptOptionId = '__default__';
  if ($('generation-lora-library-id')) $('generation-lora-library-id').value = '';
  ['generation-lora-library-name','generation-lora-library-base-model','generation-lora-library-style-category','generation-lora-library-civitai-url','generation-lora-library-triggers','generation-lora-library-keywords','generation-lora-library-example'].forEach(id => { if ($(id)) $(id).value = ''; });
  if ($('generation-lora-library-prompt-option-name')) $('generation-lora-library-prompt-option-name').value = 'Default sample';
  if ($('generation-lora-library-strength')) $('generation-lora-library-strength').value = '0.8';
  if ($('generation-lora-library-min-strength')) $('generation-lora-library-min-strength').value = '0.6';
  if ($('generation-lora-library-max-strength')) $('generation-lora-library-max-strength').value = '1.0';
  populateGenerationLoraPromptOptionSelect('__default__');
  setGenerationLoraPreviewIndex(0);
  if ($('generation-lora-library-preview-note')) $('generation-lora-library-preview-note').textContent = message;
  renderGenerationLoraMetaChips();
  setGenerationLoraLibraryEditMode(false);
}

function fillGenerationLoraBrowserSelect(entries, selected='') {
  const el = $('generation-lora-library-select');
  if (!el) return;
  el.innerHTML = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = 'Pick a scanned LoRA';
  el.appendChild(first);
  (entries || []).forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.id || '';
    opt.textContent = item.label || item.id || '';
    if (selected && selected === opt.value) opt.selected = true;
    el.appendChild(opt);
  });
}

function bestMatchGenerationLoraEntry(entries, rawName='') {
  const rawList = Array.isArray(rawName) ? rawName : [rawName];
  const names = [];
  rawList.forEach(value => {
    const raw = trim(value || '');
    if (!raw) return;
    const lower = raw.toLowerCase();
    if (!names.includes(lower)) names.push(lower);
    const slashBase = raw.split(/[\/]/).pop();
    if (slashBase) {
      const slashLower = slashBase.toLowerCase();
      if (!names.includes(slashLower)) names.push(slashLower);
    }
    const noExt = raw.replace(/\.[a-z0-9]+$/i, '');
    if (noExt) {
      const noExtLower = noExt.toLowerCase();
      if (!names.includes(noExtLower)) names.push(noExtLower);
    }
  });
  if (!names.length) return null;
  const exact = (entries || []).find(item => {
    const label = trim(item?.label || '').toLowerCase();
    const id = trim(item?.id || '').toLowerCase();
    return names.includes(label) || names.includes(id);
  });
  if (exact) return exact;
  const byBase = (entries || []).find(item => {
    const label = trim(item?.label || '').toLowerCase();
    const id = trim(item?.id || '').toLowerCase();
    return names.some(name => {
      const base = name.replace(/\.[a-z0-9]+$/i, '');
      return !!base && (label.includes(base) || id.includes(base));
    });
  });
  return byBase || (entries || [])[0] || null;
}

async function refreshGenerationLoraLibraryBrowser(options={}) {
  const keepSelection = options.keepSelection !== false;
  const preferredName = trim(options.preferredName || '');
  const overrideQuery = Object.prototype.hasOwnProperty.call(options, 'query') ? String(options.query || '') : null;
  const previous = keepSelection ? trim($('generation-lora-library-select')?.value || generationLoraLibraryState.currentLid || '') : '';
  const params = new URLSearchParams();
  params.set('kind', 'lora');
  params.set('query', overrideQuery !== null ? overrideQuery : ($('generation-lora-library-search')?.value || ''));
  params.set('category', 'all');
  params.set('base_model', 'all');
  params.set('style_category', 'all');
  try {
    const data = await safeFetchJson(`/api/neo-library/lora-browser?${params.toString()}`, { cache:'no-store' });
    const family = generationLoraCompatibilityState.family || detectGenerationCheckpointFamily();
    const sourceEntries = Array.isArray(data.entries) ? data.entries : [];
    const entries = sourceEntries.filter(item => generationLoraFamilyCompatibility(item, family).visible !== false);
    generationLoraLibraryState.entries = entries;
    const chosen = preferredName ? (bestMatchGenerationLoraEntry(entries, preferredName)?.id || '') : (previous || '');
    fillGenerationLoraBrowserSelect(entries, chosen);
    const active = chosen || trim($('generation-lora-library-select')?.value || '');
    if (active) await loadGenerationLoraLibraryRecord(active, { silent:true });
    else clearGenerationLoraLibraryDetails(entries.length ? 'Choose a saved LoRA to show its metadata here.' : 'No saved LoRA metadata matched that search yet.');
    setStatus('generation-lora-library-status', entries.length ? `${entries.length} LoRA item(s) ready.` : 'No LoRA metadata matched the current search.', entries.length ? '' : 'warn');
    return entries;
  } catch (e) {
    setStatus('generation-lora-library-status', e.message || 'Could not load the saved LoRA library.', 'error');
    return [];
  }
}

function renderGenerationLoraLibraryRecord(rec, lid='') {
  generationLoraLibraryState.currentLid = lid || generationLoraLibraryState.currentLid || '';
  generationLoraLibraryState.currentRecord = rec || null;
  generationLoraLibraryState.previewUrls = Array.isArray(rec?.preview_urls) && rec.preview_urls.length
    ? rec.preview_urls.slice()
    : (rec?.preview_url ? [{ url: rec.preview_url, path: rec.preview_image || '', name: rec?.name || 'preview' }] : []);
  generationLoraLibraryState.previewIndex = 0;
  generationLoraLibraryState.promptOptions = Array.isArray(rec?.prompt_options) ? rec.prompt_options.map(opt => ({ ...opt })) : [];
  generationLoraLibraryState.selectedPromptOptionId = '__default__';
  if ($('generation-lora-library-id')) $('generation-lora-library-id').value = generationLoraLibraryState.currentLid || '';
  if ($('generation-lora-library-name')) $('generation-lora-library-name').value = rec?.name || rec?.file || '';
  if ($('generation-lora-library-base-model')) $('generation-lora-library-base-model').value = rec?.base_model || '';
  if ($('generation-lora-library-style-category')) $('generation-lora-library-style-category').value = rec?.style_category || '';
  if ($('generation-lora-library-strength')) $('generation-lora-library-strength').value = String(rec?.default_strength ?? 0.8);
  if ($('generation-lora-library-min-strength')) $('generation-lora-library-min-strength').value = String(rec?.min_strength ?? 0.6);
  if ($('generation-lora-library-max-strength')) $('generation-lora-library-max-strength').value = String(rec?.max_strength ?? 1.0);
  if ($('generation-lora-library-civitai-url')) $('generation-lora-library-civitai-url').value = rec?.provider_url || '';
  if ($('generation-lora-library-triggers')) $('generation-lora-library-triggers').value = (rec?.triggers || []).join(', ');
  if ($('generation-lora-library-keywords')) $('generation-lora-library-keywords').value = (rec?.keywords || []).join(', ');
  if ($('generation-lora-library-example')) $('generation-lora-library-example').value = rec?.example_prompt || '';
  if ($('generation-lora-library-prompt-option-name')) $('generation-lora-library-prompt-option-name').value = 'Default sample';
  const baseBits = [trim(rec?.base_model || ''), trim(rec?.style_category || ''), trim(rec?.provider_label || '')].filter(Boolean);
  if ($('generation-lora-library-preview-note')) $('generation-lora-library-preview-note').textContent = baseBits.join(' · ') || (rec?.file || rec?.name || 'Scanned LoRA metadata ready.');
  populateGenerationLoraPromptOptionSelect('__default__');
  setGenerationLoraPreviewIndex(0);
  renderGenerationLoraMetaChips();
  setGenerationLoraLibraryEditMode(false);
}

async function loadGenerationLoraLibraryRecord(lid='', options={}) {
  const target = trim(lid || $('generation-lora-library-select')?.value || '');
  if (!target) {
    clearGenerationLoraLibraryDetails();
    return null;
  }
  try {
    const data = await safeFetchJson(`/api/neo-library/lora-record?lid=${encodeURIComponent(target)}`, { cache:'no-store' });
    renderGenerationLoraLibraryRecord(data.record || {}, target);
    if ($('generation-lora-library-select')) $('generation-lora-library-select').value = target;
    if (!options.silent) setStatus('generation-lora-library-status', 'LoRA metadata loaded.', 'success');
    return data.record || null;
  } catch (e) {
    setStatus('generation-lora-library-status', e.message || 'Could not load the selected LoRA metadata.', 'error');
    return null;
  }
}

function inspectGenerationLoraFromSelect(selectEl) {
  const selectedValue = trim(selectEl?.value || '');
  const selectedLabel = trim(selectEl?.selectedOptions?.[0]?.textContent || '');
  const candidates = [selectedLabel, selectedValue].filter(Boolean);
  if (!candidates.length) return Promise.resolve(null);
  return inspectGenerationLoraByName(candidates);
}


// Dynamic Thresholding / CFG Fix UI + payload contract bridge (Phase 5 presets + custom tuning)
(function () {
  const DT_PRESETS = {
    off: { enabled: false, preset: 'off', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 1.0, label: 'Off' },
    safe: { enabled: true, preset: 'safe', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 1.0, label: 'Safe detail' },
    detail_push: { enabled: true, preset: 'detail_push', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 0.99, label: 'Detail push' },
    aggressive: { enabled: true, preset: 'aggressive', mode: 'simple', mimic_scale: 6.0, threshold_percentile: 0.98, label: 'Aggressive pop control' },
    smart_auto: { enabled: true, preset: 'smart_auto', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 0.99, label: 'Smart auto' },
    advanced: { enabled: true, preset: 'advanced', mode: 'simple', mimic_scale: 7.0, threshold_percentile: 0.99, label: 'Custom / Advanced' },
  };

  function ge(id) { return document.getElementById(id); }
  function num(id, fallback) {
    const value = Number(ge(id)?.value);
    return Number.isFinite(value) ? value : fallback;
  }
  function smartDynamicThresholdingPreset() {
    const cfg = Number(ge('generation-cfg')?.value || 0);
    if (cfg >= 16) return { mimic_scale: 6.0, threshold_percentile: 0.98 };
    if (cfg >= 12) return { mimic_scale: 7.0, threshold_percentile: 0.99 };
    if (cfg >= 8) return { mimic_scale: 7.5, threshold_percentile: 1.0 };
    return { mimic_scale: 7.0, threshold_percentile: 1.0 };
  }
  function setDynamicThresholdingInputsFromPreset(preset) {
    const baseRaw = Object.assign({}, DT_PRESETS[preset] || DT_PRESETS.off);
    const base = preset === 'smart_auto' ? Object.assign(baseRaw, smartDynamicThresholdingPreset()) : baseRaw;
    const mimicEl = ge('generation-dynamic-thresholding-mimic');
    const percentileEl = ge('generation-dynamic-thresholding-percentile');
    if (mimicEl) mimicEl.value = Number(base.mimic_scale ?? 7.0).toFixed(1);
    if (percentileEl) percentileEl.value = Number(base.threshold_percentile ?? 1.0).toFixed(2);
  }
  function catalogDynamicThresholding() {
    const catalog = window.generationCatalogState || (typeof generationCatalogState !== 'undefined' ? generationCatalogState : null) || {};
    const dt = catalog.dynamic_thresholding || catalog.features?.dynamic_thresholding || {};
    return dt && typeof dt === 'object' ? dt : {};
  }
  function isAvailable() {
    const dt = catalogDynamicThresholding();
    return !!(dt.available || dt.simple || dt.full || (Array.isArray(dt.nodes) && dt.nodes.length));
  }
  function isDynamicThresholdingFamilyAllowed() {
    const family = String(ge('generation-family')?.value || 'sdxl_sd').toLowerCase();
    const registry = window.NeoGenerationFeatureAvailability;
    if (registry && typeof registry.isFeatureAllowed === 'function') {
      return registry.isFeatureAllowed('dynamic_thresholding', family);
    }
    return family === 'sdxl_sd' || family === 'sdxl' || family === 'sd';
  }
  function normalizeMode(mode) {
    const requested = String(mode || 'simple').toLowerCase();
    const dt = catalogDynamicThresholding();
    if (requested === 'full' && dt.full === false) return 'simple';
    if (requested === 'simple' && dt.simple === false && dt.full) return 'full';
    return requested === 'full' ? 'full' : 'simple';
  }
  function readGenerationDynamicThresholding() {
    const allowedFamily = isDynamicThresholdingFamilyAllowed();
    const preset = allowedFamily ? String(ge('generation-dynamic-thresholding-preset')?.value || 'off') : 'off';
    let base = Object.assign({}, DT_PRESETS[preset] || DT_PRESETS.off);
    if (preset === 'smart_auto') base = Object.assign(base, smartDynamicThresholdingPreset());
    const advanced = preset === 'advanced' || !!ge('generation-dynamic-thresholding-customize')?.checked;
    const mode = normalizeMode(ge('generation-dynamic-thresholding-mode')?.value || base.mode || 'simple');
    const mimic = advanced ? num('generation-dynamic-thresholding-mimic', base.mimic_scale) : base.mimic_scale;
    const percentile = advanced ? num('generation-dynamic-thresholding-percentile', base.threshold_percentile) : base.threshold_percentile;
    return {
      enabled: allowedFamily && !!base.enabled,
      preset,
      mode,
      node: mode === 'full' ? 'DynamicThresholdingFull' : 'DynamicThresholdingSimple',
      mimic_scale: Math.max(1, Math.min(30, Number(mimic || 7))),
      threshold_percentile: Math.max(0.80, Math.min(1.00, Number(percentile || 1))),
      custom_values: advanced,
      auto_disable_low_cfg: true,
      auto_disable_family: true,
      available: isAvailable(),
    };
  }
  function syncGenerationDynamicThresholdingState(source) {
    const value = readGenerationDynamicThresholding();
    if (window.NeoImageState?.updateModule) window.NeoImageState.updateModule('dynamic_thresholding', value, source || 'dynamic-thresholding-ui');
    return value;
  }
  function renderGenerationDynamicThresholding() {
    const card = ge('generation-dynamic-thresholding-card');
    if (!card) return;
    const allowedFamily = isDynamicThresholdingFamilyAllowed();
    card.style.display = allowedFamily ? '' : 'none';
    if (!allowedFamily) {
      syncGenerationDynamicThresholdingState('dynamic-thresholding-family-hidden');
      return;
    }
    const preset = ge('generation-dynamic-thresholding-preset')?.value || 'off';
    const customize = !!ge('generation-dynamic-thresholding-customize')?.checked;
    const advanced = preset === 'advanced' || customize;
    if (preset === 'advanced' && ge('generation-dynamic-thresholding-customize')) ge('generation-dynamic-thresholding-customize').checked = true;
    if (card.dataset.lastDtPreset !== preset && !customize) {
      setDynamicThresholdingInputsFromPreset(preset);
      card.dataset.lastDtPreset = preset;
    }
    if (preset === 'smart_auto' && !customize) setDynamicThresholdingInputsFromPreset(preset);
    document.querySelectorAll('.generation-dynamic-thresholding-advanced').forEach(el => { el.style.display = advanced ? '' : 'none'; });
    const dt = catalogDynamicThresholding();
    const available = isAvailable();
    const status = ge('generation-dynamic-thresholding-status');
    const mode = ge('generation-dynamic-thresholding-mode');
    if (mode) {
      Array.from(mode.options || []).forEach(opt => {
        const val = String(opt.value || '').toLowerCase();
        if (val === 'simple') opt.disabled = dt.simple === false && !!dt.full;
        if (val === 'full') opt.disabled = dt.full === false;
      });
      mode.value = normalizeMode(mode.value);
    }
    if (status) {
      const nodes = Array.isArray(dt.nodes) && dt.nodes.length ? ` · ${dt.nodes.map(n => String(n).replace('DynamicThresholding','')).join('/')}` : '';
      status.textContent = available ? `Ready${nodes}` : 'Node missing';
      status.title = available ? 'ComfyUI Dynamic Thresholding nodes detected.' : (dt.install_hint || 'Install mcmonkeyprojects/sd-dynamic-thresholding in ComfyUI/custom_nodes, then restart ComfyUI.');
    }
    const note = ge('generation-dynamic-thresholding-note');
    if (note) note.textContent = available
      ? 'SDXL-only CFG highlight control. Use Customize to edit Mimic CFG and Threshold Percentile.'
      : (dt.install_hint || 'Optional quality guard for high CFG. Install mcmonkeyprojects/sd-dynamic-thresholding in ComfyUI/custom_nodes to enable it.');
    const summary = ge('generation-dynamic-thresholding-summary');
    if (summary) {
      const cfg = Number(ge('generation-cfg')?.value || 0);
      const value = readGenerationDynamicThresholding();
      summary.textContent = !value.enabled
        ? 'Off. Enable only when high CFG starts burning contrast.'
        : `${(DT_PRESETS[value.preset]?.label || value.preset.replace('_', ' '))} · ${value.mode} · mimic ${value.mimic_scale} · percentile ${value.threshold_percentile}${cfg && cfg <= 7 ? ' · will auto-skip at current CFG' : ''}`;
    }
    syncGenerationDynamicThresholdingState('dynamic-thresholding-render');
  }
  function bindGenerationDynamicThresholding() {
    ['generation-dynamic-thresholding-preset','generation-dynamic-thresholding-mode','generation-dynamic-thresholding-mimic','generation-dynamic-thresholding-percentile','generation-dynamic-thresholding-customize','generation-cfg','generation-family'].forEach(id => {
      const el = ge(id);
      if (!el || el.dataset.dynamicThresholdingBound === '1') return;
      el.dataset.dynamicThresholdingBound = '1';
      ['input','change'].forEach(type => el.addEventListener(type, () => renderGenerationDynamicThresholding()));
    });
    if (document.body && document.body.dataset.dynamicThresholdingFamilyEventBound !== '1') {
      document.body.dataset.dynamicThresholdingFamilyEventBound = '1';
      document.addEventListener('neo-generation-family-changed', () => {
        renderGenerationDynamicThresholding();
        syncGenerationDynamicThresholdingState('dynamic-thresholding-family-event');
      });
    }
    renderGenerationDynamicThresholding();
  }

  window.readGenerationDynamicThresholding = readGenerationDynamicThresholding;
  window.renderGenerationDynamicThresholding = renderGenerationDynamicThresholding;
  window.syncGenerationDynamicThresholdingState = syncGenerationDynamicThresholdingState;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindGenerationDynamicThresholding, { once: true });
  else window.setTimeout(bindGenerationDynamicThresholding, 0);
})();
