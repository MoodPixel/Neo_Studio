(() => {
  // CN Hints Bridge → ControlNet sender (best-effort DOM search)

  async function dataUrlToFile(dataUrl, filename) {
    const res = await fetch(dataUrl);
    const blob = await res.blob();
    return new File([blob], filename, { type: blob.type || "image/png" });
  }

  function pickRoot() {
    try {
      return gradioApp();
    } catch (e) {
      return document;
    }
  }

  function findTab(tabName) {
    const root = pickRoot();
    return (
      root.querySelector(`#tab_${tabName}`) ||
      root.querySelector(`[id="tab_${tabName}"]`) ||
      root.querySelector(`[id*="${tabName}"]`)
    );
  }

  function getPreviewSrcById(elemId) {
    const root = pickRoot();
    const host = root.querySelector(`#${elemId}`);
    if (!host) return null;

    // Gradio Image usually renders an <img> tag.
    const img = host.querySelector("img");
    if (img && img.src) return img.src;

    // Fallback: sometimes canvas is used.
    const canvas = host.querySelector("canvas");
    if (canvas && canvas.toDataURL) return canvas.toDataURL("image/png");

    return null;
  }

  function getPreviewSrc() {
    return getPreviewSrcById("cnbridge_preview_img");
  }

  function nearestControlNetUnit(el) {
    if (!el) return null;
    return (
      el.closest("[id*='controlnet']") ||
      el.closest("[class*='controlnet']") ||
      el.closest("[data-testid*='controlnet']") ||
      el.closest("[id*='cn_']") ||
      el.closest("[class*='cn_']") ||
      el.parentElement
    );
  }

  function pickControlNetFileInputs(tabRoot) {
    const all = Array.from(tabRoot.querySelectorAll("input[type='file']"));
    const cn = all.filter((inp) => {
      const unit = nearestControlNetUnit(inp);
      if (!unit) return false;
      const t = (unit.id || "") + " " + (unit.className || "");
      return t.toLowerCase().includes("controlnet") || t.toLowerCase().includes("cn");
    });

    // If heuristic found nothing, at least return all file inputs as a last resort.
    return cn.length ? cn : all;
  }

  function setFileToInput(fileInput, file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    fileInput.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    fileInput.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  }

  function setSelectFirstMatch(selectEl, predicate) {
    if (!selectEl || !selectEl.options) return false;
    for (const opt of Array.from(selectEl.options)) {
      if (predicate(opt)) {
        selectEl.value = opt.value;
        selectEl.dispatchEvent(new Event("change", { bubbles: true }));
        selectEl.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
      }
    }
    return false;
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function textOf(el) {
    return ((el && (el.textContent || el.innerText)) || "").trim().toLowerCase();
  }

  function optionMatches(text, wants) {
    const t = (text || "").trim().toLowerCase();
    return wants.some((w) => t.includes(w));
  }

  function findLabeledContainer(root, labelKeywords) {
    const labels = Array.from(root.querySelectorAll("label, span, div, p"));
    for (const el of labels) {
      const t = textOf(el);
      if (!t) continue;
      if (!labelKeywords.some((k) => t.includes(k))) continue;
      let node = el;
      for (let i = 0; i < 4 && node; i += 1) {
        const hasCombo = node.querySelector && node.querySelector("select, [role='combobox'], input");
        if (hasCombo) return node;
        node = node.parentElement;
      }
    }
    return null;
  }

  async function selectCustomDropdown(container, wants) {
    if (!container) return false;
    const native = container.querySelector("select");
    if (native) {
      return setSelectFirstMatch(native, (opt) => optionMatches(opt.textContent || opt.value || "", wants));
    }

    const combo = container.querySelector("[role='combobox'], input, button");
    if (!combo) return false;
    combo.click();
    combo.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    await sleep(120);

    const root = pickRoot();
    const options = Array.from(root.querySelectorAll("[role='option'], li, button, div"));
    const match = options.find((el) => optionMatches(textOf(el), wants));
    if (!match) {
      if (combo.blur) combo.blur();
      return false;
    }
    match.click();
    match.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    match.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    await sleep(80);
    return true;
  }

  async function tryAutoConfig(unitRoot, kind, mode) {
    if (!unitRoot) return;
    const k = String(kind || "").toLowerCase();
    const sourceMode = String(mode || "hint").toLowerCase();
    const aliases = {
      canny: ["canny"],
      openpose: ["openpose", "open pose", "pose"],
      depth: ["depth"],
      composition: ["composition", "reference", "shuffle"],
      "ip-adapter": ["ip-adapter", "ip adapter", "adapter"],
    };
    const wants = aliases[k] || [k];
    const selects = Array.from(unitRoot.querySelectorAll("select"));

    // Native <select> first.
    if (sourceMode === "hint" && ["canny", "openpose", "depth"].includes(k)) {
      for (const sel of selects) {
        setSelectFirstMatch(sel, (opt) => {
          const t = textOf(opt);
          return t === "none" || t.startsWith("none");
        });
      }
    }

    for (const sel of selects) {
      setSelectFirstMatch(sel, (opt) => optionMatches(opt.textContent || opt.value || "", wants));
    }

    // Gradio/custom dropdown fallback.
    if (sourceMode === "source") {
      if (["canny", "openpose", "depth"].includes(k)) {
        await selectCustomDropdown(findLabeledContainer(unitRoot, ["preprocessor", "module", "processor", "control type"]), wants);
      }
      await selectCustomDropdown(findLabeledContainer(unitRoot, ["model", "control model", "model name", "control type"]), wants);
    } else {
      if (["canny", "openpose", "depth"].includes(k)) {
        await selectCustomDropdown(findLabeledContainer(unitRoot, ["preprocessor", "module", "processor"]), ["none"]);
      }
      await selectCustomDropdown(findLabeledContainer(unitRoot, ["model", "control model", "model name", "control type"]), wants);
    }

    if (k === "ip-adapter") {
      await selectCustomDropdown(findLabeledContainer(unitRoot, ["module", "preprocessor", "adapter"]), wants);
      await selectCustomDropdown(findLabeledContainer(unitRoot, ["model", "adapter model", "control model"]), wants);
    }
  }

  // Global function used by python _js callbacks
  window.cnbridgeSendFromPreview = async function (tabName, unitIdx, kind, autoConfig, previewId, mode) {

    try {
      const src = getPreviewSrcById(previewId || "cnbridge_preview_img");
      if (!src) {
        alert("CN Bridge: preview image not found. Select a hint file first.");
        return;
      }

      // Note: Gradio can sometimes render blob: URLs; fetch still works.
      const file = await dataUrlToFile(src, `cnbridge_${kind || "hint"}.png`);

      const tab = findTab(tabName);
      if (!tab) {
        alert(`CN Bridge: could not find tab '${tabName}'.`);
        return;
      }

      const inputs = pickControlNetFileInputs(tab);
      if (!inputs.length) {
        alert("CN Bridge: could not locate any file inputs in the target tab.");
        return;
      }

      const idx = Math.max(0, Math.min(parseInt(unitIdx || 0, 10), inputs.length - 1));
      const target = inputs[idx];

      setFileToInput(target, file);

      if (autoConfig) {
        const unitRoot = nearestControlNetUnit(target);
        await tryAutoConfig(unitRoot, kind, mode || 'hint');
      }
    } catch (err) {
      console.error(err);
      alert("CN Bridge: send failed. Open DevTools console for details.");
    }
  };

  // Backwards-compatible name used by earlier builds
  window.cnbridgeSendToControlNet = async function (tabName, unitIdx, kind, autoConfig) {
    return window.cnbridgeSendFromPreview(tabName, unitIdx, kind, autoConfig, "cnbridge_preview_img", 'hint');
  };

  window.cnbridgeSendBoth = async function (tabName, cannyUnitIdx, poseUnitIdx, autoConfig, cannyPreviewId, posePreviewId) {
    // Fire sequentially to keep DOM changes predictable.
    await window.cnbridgeSendFromPreview(tabName, cannyUnitIdx, "canny", autoConfig, cannyPreviewId || "cnbridge_preview_canny", 'hint');
    await window.cnbridgeSendFromPreview(tabName, poseUnitIdx, "openpose", autoConfig, posePreviewId || "cnbridge_preview_pose", 'hint');
  };

  // Count available ControlNet units by counting file inputs in the tab.
  // Used to auto-size unit sliders.
  window.cnbridgeDetectUnitCount = function (tabName) {
    try {
      const tab = findTab(tabName);
      if (!tab) return 0;
      const inputs = pickControlNetFileInputs(tab);
      return inputs.length || 0;
    } catch (e) {
      return 0;
    }
  };
})();
