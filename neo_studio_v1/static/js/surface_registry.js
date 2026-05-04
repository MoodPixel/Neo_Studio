(function () {
  const bootSurfaces = Array.isArray(window.NEO_STUDIO_BOOT?.surfaceDefinitions)
    ? window.NEO_STUDIO_BOOT.surfaceDefinitions.slice()
    : [];

  const ACTIVATION_HOOKS = {
    generate() {
      if (typeof getRoleSession === 'function' && getRoleSession('image')?.connected) {
        if (typeof refreshGenerationCatalog === 'function') refreshGenerationCatalog(true).catch(() => {});
        if (typeof fetchGenerationState === 'function') fetchGenerationState(true).catch(() => {});
      }
    },
    video() {
      if (typeof window.neoRefreshVideoSurface === 'function') window.neoRefreshVideoSurface();
    },
    voice() {
      if (typeof window.neoRefreshVoiceSurface === 'function') window.neoRefreshVoiceSurface();
    },
    audio() {
      if (typeof window.neoRefreshAudioSurface === 'function') window.neoRefreshAudioSurface();
    },
    board() {
      if (typeof window.neoRefreshBoardSurface === 'function') window.neoRefreshBoardSurface();
    },
    manager() {},
    roleplay_v2() {
      if (typeof window.neoRefreshRoleplayV2Surface === 'function') window.neoRefreshRoleplayV2Surface();
      if (typeof document !== 'undefined') {
        window.setTimeout(() => document.getElementById('roleplay-v2-scene-user-input')?.focus() || document.getElementById('roleplay-v2-project-select')?.focus(), 0);
      }
    },
    assistant() {
      if (typeof window.neoRefreshAssistantSurface === 'function') window.neoRefreshAssistantSurface();
      if (typeof document !== 'undefined') {
        window.setTimeout(() => document.getElementById('assistant-composer')?.focus(), 0);
      }
    },
    admin() {
      if (typeof fetchNodeManagerState === 'function') fetchNodeManagerState(true).catch(() => {});
    },
  };

  const SURFACE_REGISTRY = {};
  bootSurfaces
    .slice()
    .sort((a, b) => Number(a?.nav_order || 999) - Number(b?.nav_order || 999))
    .forEach(surface => {
      if (!surface?.id) return;
      SURFACE_REGISTRY[surface.id] = {
        id: surface.id,
        label: surface.label || surface.id,
        nav_order: Number(surface.nav_order || 999),
        maturity: surface.maturity || 'stable',
        sectionId: surface.section_id || `tab-${surface.id}`,
        requiredBackends: Array.isArray(surface.required_backend_roles) ? surface.required_backend_roles.slice() : [],
        optionalBackends: Array.isArray(surface.optional_backend_roles) ? surface.optional_backend_roles.slice() : [],
        lazyModule: surface.lazy_module || surface.id,
        helperEnabled: !!surface.helper_enabled,
        showBackendChip: !!surface.show_backend_chip,
        adminSectionKey: surface.admin_section_key || null,
        devOnly: !!surface.dev_only,
        enabled: surface.enabled !== false,
        onEnter: ACTIVATION_HOOKS[surface.id] || function () {},
      };
    });

  function getSurface(surfaceId) {
    return SURFACE_REGISTRY[surfaceId] || null;
  }

  function listSurfaces() {
    return Object.values(SURFACE_REGISTRY)
      .filter(surface => surface.enabled !== false)
      .sort((a, b) => Number(a.nav_order || 999) - Number(b.nav_order || 999));
  }

  function resolveSectionId(surfaceId) {
    return getSurface(surfaceId)?.sectionId || `tab-${surfaceId}`;
  }

  function runActivation(surfaceId) {
    const surface = getSurface(surfaceId);
    surface?.onEnter?.();
  }

  function getBackendUsage(surfaceId) {
    const surface = getSurface(surfaceId) || {};
    return {
      required: Array.isArray(surface.requiredBackends) ? surface.requiredBackends.slice() : [],
      optional: Array.isArray(surface.optionalBackends) ? surface.optionalBackends.slice() : [],
    };
  }

  window.NeoSurfaceRegistry = {
    getSurface,
    listSurfaces,
    resolveSectionId,
    runActivation,
    getBackendUsage,
  };
})();
