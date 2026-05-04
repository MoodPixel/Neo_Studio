(function () {
  function text(value) { return String(value || '').trim(); }

  function targetKind(target = '') {
    const clean = text(target).toLowerCase();
    if (clean === 'world') return 'world';
    if (clean === 'scenario') return 'scenario';
    return 'character';
  }

  function applyToV2Forge(reply, target = '') {
    const core = window.neoRoleplayV2;
    if (!core) {
      return { ok: false, message: 'Roleplay V2 is not ready yet. Open the Roleplay workspace once and try again.' };
    }
    const kind = targetKind(target);
    if (typeof window.switchTab === 'function') window.switchTab('roleplay_v2');
    try { core.setSubtab?.('forge'); } catch (_) {}
    const run = async () => {
      const state = core.state || {};
      state.forge = state.forge || {};
      state.forge.selectedKind = kind;
      state.forge.selectedRecordId = '';
      state.forge.workingPayload = null;
      await core.modules?.forge?.loadForgeState?.();
      const mdEditor = document.getElementById('roleplay-v2-forge-md-editor');
      if (mdEditor) mdEditor.value = String(reply || '').trim();
      document.querySelector('[data-roleplay-v2-forge-view="md"]')?.click();
      document.getElementById('btn-roleplay-v2-forge-apply-md')?.click();
      window.neoRoleplayV2?.setStatus?.('roleplay-v2-forge-status', `Loaded Assistant draft into a new ${kind} record in Forge. Review and save it.`, 'success');
    };
    run().catch(err => window.neoRoleplayV2?.setStatus?.('roleplay-v2-forge-status', err.message || String(err), 'error'));
    return {
      ok: true,
      message: `Loaded the Assistant draft into Roleplay Forge as a new ${kind} record. Review and save it before compiling.`,
    };
  }

  window.NeoRoleplayHelperBridge = {
    applyAssistantDraftFromText(reply, target, _options = {}) {
      return applyToV2Forge(reply, target);
    },
    applyLastAssistantDraft() {
      return { ok: false, message: 'Legacy Roleplay helper write-back was retired. Use the Roleplay V2 workspace instead.' };
    },
  };
})();
