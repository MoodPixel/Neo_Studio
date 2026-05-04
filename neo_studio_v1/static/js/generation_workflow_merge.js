(function () {
  const ROOT_SELECTOR = '#tab-generate';
  const MERGE_DELAY_MS = 80;

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function queryAccordion(id) {
    return document.querySelector(`${ROOT_SELECTOR} [data-accordion-id="${id}"]`);
  }

  function accordionBody(node) {
    return node?.querySelector(':scope > .accordion-body') || null;
  }

  function makeStepNote(id, title, copy, steps) {
    const note = document.createElement('div');
    note.id = id;
    note.className = 'generation-step-note';
    note.innerHTML = `
      <div class="generation-step-note-head">
        <div class="generation-step-note-title">${title}</div>
        <div class="generation-step-note-copy">${copy}</div>
      </div>
      <div class="generation-step-chip-row">${(steps || []).map(step => `<span class="generation-step-chip">${step}</span>`).join('')}</div>`;
    return note;
  }

  function ensurePrepended(parent, child) {
    if (!parent || !child) return;
    if (child.parentElement === parent && parent.firstChild === child) return;
    if (child.parentElement !== parent) parent.prepend(child);
    else parent.insertBefore(child, parent.firstChild);
  }

  function ensureNested(parentId, childId, wrapperId, title, copy, steps) {
    const parent = queryAccordion(parentId);
    const child = queryAccordion(childId);
    const parentBody = accordionBody(parent);
    if (!parent || !child || !parentBody) return false;

    let wrapper = parentBody.querySelector(`#${wrapperId}`);
    if (!wrapper) {
      wrapper = document.createElement('div');
      wrapper.id = wrapperId;
      wrapper.className = 'generation-nested-shell';
      wrapper.appendChild(makeStepNote(`${wrapperId}-note`, title, copy, steps));
      parentBody.appendChild(wrapper);
    }
    if (child.parentElement !== wrapper) wrapper.appendChild(child);
    child.classList.add('generation-nested-accordion');
    child.open = false;
    return true;
  }

  function ensureBodyNote(parentId, noteId, title, copy, steps) {
    const parent = queryAccordion(parentId);
    const body = accordionBody(parent);
    if (!body) return false;
    let note = body.querySelector(`#${noteId}`);
    if (!note) {
      note = makeStepNote(noteId, title, copy, steps);
    }
    ensurePrepended(body, note);
    return true;
  }

  function ensureHostNote(hostId, noteId, title, copy, steps) {
    const host = document.getElementById(hostId);
    if (!host) return false;
    let note = host.querySelector(`#${noteId}`);
    if (!note) note = makeStepNote(noteId, title, copy, steps);
    ensurePrepended(host, note);
    return true;
  }


  function getActiveGenerationFamily() {
    try { return String(window.NeoGenerationFamilyRouter?.getActiveFamily?.() || $('generation-family')?.value || '').trim(); }
    catch (_) { return String($('generation-family')?.value || '').trim(); }
  }

  function applyWorkflowMerge() {
    const activeFamily = getActiveGenerationFamily();
    const isQwen = activeFamily === 'qwen_image_edit';

    if (!isQwen) {
      ensureBodyNote(
        'generation-ipadapter-settings',
        'generation-reference-order-note',
        'Reference workflow order',
        'Pick an identity preset first when you need same-face, same-character, or style carry-over, then fine-tune the IP-Adapter controls below it.',
        ['Identity preset first', 'IP-Adapter / FaceID tuning second', 'ControlNet only if structure matters']
      );
    }

    // Repair system: keep raw mask override inside the inpaint path, not as a peer-level first-step section.
    ensureNested(
      'generation-inpaint-controls',
      'generation-mask-raw-upload',
      'generation-repair-advanced-mask-shell',
      'Advanced mask override',
      'This is for prepared black/white masks that already align with the source image. Keep it inside the repair path instead of treating it like a top-level workflow.',
      ['1 Choose target', '2 Paint or load mask', '3 Use raw mask only if you already prepared one']
    );

    ensureBodyNote(
      'Repair workflow order',
      'Use cleanup staging first when you are removing or isolating content, then move into mask/inpaint, then use detail repair only if a local area still needs help.',
      ['Cleanup prep', 'Mask + inpaint', 'Selective repair']
    );

    ensureBodyNote(
      'generation-inpaint-controls',
      'generation-inpaint-order-note',
      'Targeted repair sequence',
      'This is the center of the replace/fix path. Keep the mask target stable before turning on heavier repair helpers.',
      ['Target area', 'Context + fill', 'Advanced mask only if needed']
    );

    // Finish system: make the order explicit in the finish lane.
    ensureHostNote(
      'generation-enhance-tab-host',
      'generation-finish-order-note',
      'Finish workflow order',
      'Use the finish lane in sequence so heavier cleanup does not get turned on too early.',
      ['Upscale Lab first', 'Selective Repair (ADetailer) if needed', 'SUPIR last and only when necessary']
    );
  }

  let mergeTimer = null;
  function scheduleMerge() {
    window.clearTimeout(mergeTimer);
    mergeTimer = window.setTimeout(applyWorkflowMerge, MERGE_DELAY_MS);
  }

  function bindTriggers() {
    document.addEventListener('click', event => {
      const target = event.target && event.target.closest
        ? event.target.closest('[data-generation-setup-tab], [data-generation-goal], [data-generation-mode]')
        : null;
      if (target) scheduleMerge();
    });
  }

  document.addEventListener('neo-generation-layout-mounted', scheduleMerge);

  ready(() => {
    bindTriggers();
    scheduleMerge();
  });
})();
