(function () {
  const FALLBACK_BLUEPRINT = {
    status_language: {
      toggle: { active: 'Enabled', inactive: 'Disabled' },
      selection: { active: 'Ready', inactive: 'Empty' },
      hybrid: { active: 'Enabled', inactive: 'Disabled' },
    },
  };

  function blueprint() {
    return window.NeoGenerationSectionBlueprint || FALLBACK_BLUEPRINT;
  }

  function getSpec(sectionOrId) {
    if (!sectionOrId) return null;
    if (typeof sectionOrId === 'object' && sectionOrId.id) return sectionOrId;
    if (typeof window.getNeoGenerationSectionSpec === 'function') return window.getNeoGenerationSectionSpec(sectionOrId);
    return null;
  }

  function safeAccordionSlug(accordionId='') {
    return String(accordionId || '')
      .trim()
      .replace(/[^a-z0-9]+/gi, '-')
      .replace(/^-+|-+$/g, '') || 'generation-section';
  }

  function badgeIdsForAccordion(accordionId='') {
    const slug = safeAccordionSlug(accordionId);
    return {
      primaryId: `${slug}-state-badge`,
      detailId: `${slug}-meta-badge`,
    };
  }

  function badgeClassFromTone(tone='enabled') {
    const key = String(tone || '').toLowerCase();
    if (['enabled', 'ready', 'on', 'active'].includes(key)) return 'is-enabled';
    if (['detail', 'meta', 'count', 'mode', 'summary'].includes(key)) return 'is-detail';
    return 'is-disabled';
  }

  function languageForSpec(spec) {
    const stateType = String(spec?.state_type || 'hybrid');
    return blueprint()?.status_language?.[stateType] || FALLBACK_BLUEPRINT.status_language.hybrid;
  }

  function primaryTextForSpec(spec, payload={}) {
    const override = String(payload.primaryText || '').trim();
    if (override) return override;
    const language = languageForSpec(spec);
    return payload.active ? language.active : language.inactive;
  }

  function primaryToneForSpec(payload={}) {
    if (payload.primaryTone) return payload.primaryTone;
    return payload.active ? 'enabled' : 'disabled';
  }

  function resolveCountText(payload={}) {
    const count = Number(payload.count || 0);
    const label = String(payload.countLabel || 'selected').trim() || 'selected';
    if (count > 0) return `${count} ${label}`;
    return '';
  }

  function detailStateForSpec(spec, payload={}) {
    const explicit = String(payload.detailText || '').trim();
    if (explicit) return {
      text: explicit,
      tone: payload.detailTone || 'detail',
    };
    const pattern = String(spec?.status_pattern?.secondary || 'custom').toLowerCase();
    if (!payload.active && payload.zeroLabel) {
      return {
        text: String(payload.zeroLabel || '').trim(),
        tone: payload.zeroTone || 'disabled',
      };
    }
    if (!payload.active && !payload.showDetailWhenInactive) {
      return { text: '', tone: 'detail' };
    }
    if (pattern === 'mode') {
      return {
        text: String(payload.modeLabel || '').trim(),
        tone: payload.detailTone || 'detail',
      };
    }
    if (pattern === 'count') {
      return {
        text: resolveCountText(payload),
        tone: payload.detailTone || 'detail',
      };
    }
    if (pattern === 'single_name') {
      const singleName = String(payload.singleName || '').trim();
      const maxNameLength = Number(payload.maxNameLength || 24);
      if (singleName && singleName.length <= maxNameLength) {
        return {
          text: singleName,
          tone: payload.detailTone || 'detail',
        };
      }
      return {
        text: resolveCountText(payload),
        tone: payload.detailTone || 'detail',
      };
    }
    return {
      text: '',
      tone: payload.detailTone || 'detail',
    };
  }

  function ensureHeaderBadges(accordionId, primaryId, detailId) {
    const block = document.querySelector(`[data-accordion-id="${accordionId}"]`);
    const title = block?.querySelector(':scope > summary .accordion-title') || block?.querySelector('.accordion-title');
    if (!title) return { primary:null, detail:null, rail:null };
    title.classList.add('generation-title-with-state');
    let rail = title.querySelector('.generation-section-state-rail');
    if (!rail) {
      rail = document.createElement('span');
      rail.className = 'generation-section-state-rail';
      title.appendChild(rail);
    }
    let primary = primaryId ? document.getElementById(primaryId) : null;
    if (primaryId && !primary) {
      primary = document.createElement('span');
      primary.id = primaryId;
      primary.className = 'generation-section-state-badge';
      rail.appendChild(primary);
    } else if (primary && primary.parentElement !== rail) {
      rail.appendChild(primary);
    }
    let detail = detailId ? document.getElementById(detailId) : null;
    if (detailId && !detail) {
      detail = document.createElement('span');
      detail.id = detailId;
      detail.className = 'generation-section-state-badge is-detail';
      rail.appendChild(detail);
    } else if (detail && detail.parentElement !== rail) {
      rail.appendChild(detail);
    }
    return { primary, detail, rail };
  }

  function setHeaderState(sectionOrId, payload={}) {
    const spec = getSpec(sectionOrId) || { id: String(sectionOrId || '') };
    if (!spec?.id) return;
    const ids = badgeIdsForAccordion(spec.id);
    const primaryId = payload.primaryId || ids.primaryId;
    const detailId = payload.detailId === null ? null : (payload.detailId || ids.detailId);
    const { primary, detail } = ensureHeaderBadges(spec.id, primaryId, detailId);
    const primaryText = primaryTextForSpec(spec, payload);
    const primaryTone = primaryToneForSpec(payload);
    const detailState = detailStateForSpec(spec, payload);
    if (primary) {
      primary.textContent = primaryText;
      primary.className = `generation-section-state-badge ${badgeClassFromTone(primaryTone)}`;
      primary.style.display = primaryText ? '' : 'none';
    }
    if (detail) {
      const detailText = String(detailState?.text || '').trim();
      detail.textContent = detailText;
      detail.className = `generation-section-state-badge ${badgeClassFromTone(detailState?.tone || 'detail')}`;
      detail.style.display = detailText ? '' : 'none';
    }
  }

  window.NeoGenerationAccordionSystem = {
    badgeClassFromTone,
    badgeIdsForAccordion,
    ensureHeaderBadges,
    primaryTextForSpec,
    setHeaderState,
  };
})();
