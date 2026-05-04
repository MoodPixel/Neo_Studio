(function () {
  const ROOT_SELECTOR = '#tab-generate';

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  }

  function getRegistry() {
    return Array.isArray(window.NeoGenerationSectionRegistry) ? window.NeoGenerationSectionRegistry : [];
  }

  function getRoot() {
    return document.querySelector(ROOT_SELECTOR);
  }

  function resolveSectionNode(id) {
    const accordion = document.querySelector(`${ROOT_SELECTOR} [data-accordion-id="${id}"]`);
    if (accordion) return accordion;
    const spec = window.getNeoGenerationSectionSpec?.(id);
    const selectors = Array.isArray(spec?.selectors) ? spec.selectors : [];
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      if (node) return node.closest('.accordion-block, .panel, .card, .shell') || node;
    }
    return null;
  }

  function applyContract(node, spec) {
    if (!node || !spec) return false;
    node.dataset.sectionContract = '1';
    node.dataset.sectionId = spec.id || '';
    node.dataset.ownerSurface = spec.owner_surface || '';
    node.dataset.sectionLevel = spec.level || '';
    node.dataset.managementMode = spec.management_mode || '';
    node.dataset.costLevel = spec.cost_level || '';
    node.dataset.hostTab = spec.host_tab || '';
    node.dataset.visibilityMode = spec.visibility_mode || '';
    node.dataset.goalCategories = Array.isArray(spec.goal_categories) ? spec.goal_categories.join(',') : '';
    node.dataset.ownerModule = spec.owner_module || '';

    if (spec.level) node.classList.add(`generation-contract-level-${spec.level}`);
    if (spec.visibility_mode) node.classList.add(`generation-contract-visibility-${spec.visibility_mode}`);
    return true;
  }

  function mountContracts() {
    const root = getRoot();
    const registry = getRegistry();
    if (!root || !registry.length) return false;

    const applied = [];
    const missing = [];

    registry.forEach(spec => {
      const node = resolveSectionNode(spec.id);
      if (!node) {
        missing.push(spec.id);
        return;
      }
      if (applyContract(node, spec)) applied.push(spec.id);
    });

    window.NeoGenerationSectionContracts = Object.freeze({
      applied_ids: applied.slice(),
      missing_ids: missing.slice(),
      total_registry_sections: registry.length,
      mounted_at: Date.now(),
    });

    document.dispatchEvent(new CustomEvent('neo-generation-contracts-mounted', {
      detail: {
        applied_ids: applied.slice(),
        missing_ids: missing.slice(),
        total_registry_sections: registry.length,
      }
    }));

    if (missing.length) {
      console.warn('[Neo Generation Contracts] Registry sections missing from current DOM:', missing.join(', '));
    }
    return true;
  }

  function boot(attempt = 0) {
    if (mountContracts()) return;
    if (attempt < 40) window.setTimeout(() => boot(attempt + 1), 150);
  }

  document.addEventListener('neo-generation-layout-mounted', () => window.setTimeout(() => boot(0), 100));
  ready(() => boot(0));
})();
