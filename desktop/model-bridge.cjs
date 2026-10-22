// Assistant-page model bridge: status read, in-place switch, startup auto-configure.
// The credential stays in the OS-protected store; every send still needs the
// native confirmation window. Auto-configure only restores the process-local
// runtime from the owner's persisted choice.
const MODELS = ['deepseek-flash', 'deepseek-v4-pro'];

const denied = code => ({ ok: false, ...(code ? { code } : {}) });

function validRuntime(value) {
  return value && typeof value === 'object' && !Array.isArray(value) &&
    ['unavailable', 'unconfigured', 'configured'].includes(value.state) &&
    (value.state === 'configured' ? MODELS.includes(value.model) : value.model === null);
}

function registerAssistantModelBridge({ ipcMain, runtime, isAllowed, persist }) {
  if (typeof isAllowed !== 'function' || typeof persist !== 'function' || !runtime)
    throw new TypeError('MODEL_BRIDGE_INVALID');
  ipcMain.handle('desktop:assistant-model-status', event => {
    if (!isAllowed(event)) return denied();
    const view = runtime.status()?.runtime;
    return validRuntime(view) ? { ok: true, runtime: view } : denied('BLOCKED_LIVE');
  });
  ipcMain.handle('desktop:assistant-model-switch', async event => {
    if (!isAllowed(event)) return denied();
    const current = runtime.status()?.runtime;
    if (!validRuntime(current)) return denied('BLOCKED_LIVE');
    if (current.state !== 'configured') return denied('UNCONFIGURED');
    const next = current.model === MODELS[0] ? MODELS[1] : MODELS[0];
    let result;
    try { result = await runtime.configure(next); } catch { return denied('BLOCKED_LIVE'); }
    const view = result?.runtime;
    if (result?.ok === true && validRuntime(view) && view.state === 'configured' && view.model === next) {
      persist(next);
      return { ok: true, runtime: view };
    }
    return { ok: false, code: typeof result?.code === 'string' ? result.code : 'BLOCKED_LIVE',
      ...(validRuntime(view) ? { runtime: view } : {}) };
  });
}

// Restore the process-local runtime from the persisted choice; failure stays silent
// and leaves the settings page as the manual fallback.
async function autoConfigureModel({ settings, runtime }) {
  if (!MODELS.includes(settings?.model) || !runtime) return false;
  try {
    const result = await runtime.configure(settings.model);
    return result?.ok === true;
  } catch { return false; }
}

module.exports = { registerAssistantModelBridge, autoConfigureModel, ASSISTANT_MODELS: MODELS };
