(function () {
  'use strict';

  const STUDIO_CONFIG = {
    prompt: [
      ['prompt-preset-details', 'Preset'],
      ['prompt-cleanup', 'Cleanup'],
      ['recent-work', 'Recent'],
      ['saved-prompts', 'Saved'],
      ['character-library', 'Characters'],
      ['prompt-helper', 'Helper'],
    ],
    caption: [
      ['caption-preset-details', 'Preset'],
      ['caption-browser', 'Browser'],
      ['reusable-component', 'Components'],
      ['batch-captioning', 'Batch'],
      ['caption-helper', 'Helper'],
    ],
  };

  function slugSafe(value) {
    return String(value || '').replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
  }

  function makeButton(studio, key, label, index) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'studio-left-tab-button';
    button.dataset.studioLeftTabButton = key;
    button.dataset.studio = studio;
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
    button.setAttribute('aria-controls', `${studio}-left-panel-${slugSafe(key)}`);
    button.textContent = label;
    return button;
  }

  function normalizePanel(panel, studio, key, index) {
    panel.classList.add('studio-left-tab-panel');
    panel.dataset.studioLeftTabPanel = key;
    panel.id = panel.id || `${studio}-left-panel-${slugSafe(key)}`;
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', `${studio}-left-tab-${slugSafe(key)}`);
    if (index !== 0) {
      panel.hidden = true;
      panel.classList.remove('is-active');
    } else {
      panel.hidden = false;
      panel.classList.add('is-active');
      if (panel.tagName.toLowerCase() === 'details') panel.open = true;
    }
  }

  function setActiveTab(rail, studio, key) {
    const buttons = rail.querySelectorAll('[data-studio-left-tab-button]');
    const panels = rail.querySelectorAll('[data-studio-left-tab-panel]');
    buttons.forEach((button) => {
      const active = button.dataset.studioLeftTabButton === key;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.tabIndex = active ? 0 : -1;
    });
    panels.forEach((panel) => {
      const active = panel.dataset.studioLeftTabPanel === key;
      panel.hidden = !active;
      panel.classList.toggle('is-active', active);
      if (active && panel.tagName.toLowerCase() === 'details') panel.open = true;
    });
    rail.dataset.activeLeftTab = key;
    try {
      window.localStorage.setItem(`neo:${studio}:left-tab`, key);
    } catch (err) {
      // Local storage is optional; keep the UI working in restricted contexts.
    }
  }

  function bindKeyboard(tablist, rail, studio) {
    tablist.addEventListener('keydown', (event) => {
      const tabs = Array.from(tablist.querySelectorAll('[data-studio-left-tab-button]'));
      const currentIndex = tabs.indexOf(document.activeElement);
      if (currentIndex < 0) return;
      let nextIndex = currentIndex;
      if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length;
      else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') nextIndex = 0;
      else if (event.key === 'End') nextIndex = tabs.length - 1;
      else return;
      event.preventDefault();
      const next = tabs[nextIndex];
      next.focus();
      setActiveTab(rail, studio, next.dataset.studioLeftTabButton);
    });
  }

  function initRail(studio) {
    const rail = document.querySelector(`[data-studio-left-rail="${studio}"]`);
    if (!rail || rail.dataset.stage4TabsReady === 'true') return;
    const config = STUDIO_CONFIG[studio] || [];
    if (!config.length) return;

    const tablist = document.createElement('div');
    tablist.className = 'studio-left-tablist';
    tablist.dataset.studioLeftTablist = studio;
    tablist.setAttribute('role', 'tablist');
    tablist.setAttribute('aria-label', `${studio} utility panels`);

    const existingByKey = new Map();
    rail.querySelectorAll('[data-stage3-left-section]').forEach((panel) => {
      existingByKey.set(panel.dataset.stage3LeftSection, panel);
    });

    config.forEach(([key, label], index) => {
      const panel = existingByKey.get(key);
      if (!panel) return;
      const button = makeButton(studio, key, label, index);
      button.id = `${studio}-left-tab-${slugSafe(key)}`;
      button.addEventListener('click', () => setActiveTab(rail, studio, key));
      tablist.appendChild(button);
      normalizePanel(panel, studio, key, index);
      rail.appendChild(panel);
    });

    const heading = rail.querySelector('.studio-left-rail-heading');
    if (heading && heading.nextSibling) rail.insertBefore(tablist, heading.nextSibling);
    else rail.insertBefore(tablist, rail.firstChild);

    bindKeyboard(tablist, rail, studio);
    rail.dataset.stage4TabsReady = 'true';

    let stored = null;
    try {
      stored = window.localStorage.getItem(`neo:${studio}:left-tab`);
    } catch (err) {}
    const firstKey = config.find(([key]) => existingByKey.has(key))?.[0];
    const startKey = stored && existingByKey.has(stored) ? stored : firstKey;
    if (startKey) setActiveTab(rail, studio, startKey);
  }

  function initAll() {
    initRail('prompt');
    initRail('caption');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll, { once: true });
  } else {
    initAll();
  }

  window.NeoPromptCaptionLeftTabs = {
    init: initAll,
    setActive: function (studio, key) {
      const rail = document.querySelector(`[data-studio-left-rail="${studio}"]`);
      if (rail) setActiveTab(rail, studio, key);
    },
  };
})();
