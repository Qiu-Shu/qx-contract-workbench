const { test } = require('node:test');
const assert = require('node:assert/strict');
const { registerAssistantModelBridge, autoConfigureModel } = require('../model-bridge.cjs');

function fixture({ state = 'configured', model = 'deepseek-flash', configure } = {}) {
  const handlers = new Map(), persisted = [], calls = [];
  const runtime = {
    status: () => ({ ok: true, runtime: { state, model: state === 'configured' ? model : null } }),
    configure: async next => {
      calls.push(next);
      if (configure) return configure(next);
      model = next; state = 'configured';
      return { ok: true, runtime: { state: 'configured', model: next } };
    },
  };
  const ipcMain = { handle(name, fn) { assert(!handlers.has(name)); handlers.set(name, fn); } };
  registerAssistantModelBridge({ ipcMain, runtime, isAllowed: event => event === 'allowed',
    persist: value => persisted.push(value) });
  return { handlers, persisted, calls, runtime };
}

test('assistant model status is only served to an allowed page and validated', async () => {
  const f = fixture();
  assert.deepEqual(await f.handlers.get('desktop:assistant-model-status')('denied'), { ok: false });
  assert.deepEqual(await f.handlers.get('desktop:assistant-model-status')('allowed'),
    { ok: true, runtime: { state: 'configured', model: 'deepseek-flash' } });
  const broken = fixture();
  broken.runtime.status = () => ({ ok: true, runtime: { state: 'configured', model: 'other' } });
  assert.deepEqual(await broken.handlers.get('desktop:assistant-model-status')('allowed'),
    { ok: false, code: 'BLOCKED_LIVE' });
});

test('assistant model switch toggles the two known models and persists only on success', async () => {
  const f = fixture();
  const first = await f.handlers.get('desktop:assistant-model-switch')('allowed');
  assert.deepEqual(first, { ok: true, runtime: { state: 'configured', model: 'deepseek-v4-pro' } });
  const second = await f.handlers.get('desktop:assistant-model-switch')('allowed');
  assert.deepEqual(second, { ok: true, runtime: { state: 'configured', model: 'deepseek-flash' } });
  assert.deepEqual(f.calls, ['deepseek-v4-pro', 'deepseek-flash']);
  assert.deepEqual(f.persisted, ['deepseek-v4-pro', 'deepseek-flash']);
});

test('assistant model switch refuses strangers, the unconfigured and failed configures', async () => {
  const f = fixture();
  assert.deepEqual(await f.handlers.get('desktop:assistant-model-switch')('denied'), { ok: false });
  assert.deepEqual(f.calls, []);
  const unconfigured = fixture({ state: 'unconfigured' });
  assert.deepEqual(await unconfigured.handlers.get('desktop:assistant-model-switch')('allowed'),
    { ok: false, code: 'UNCONFIGURED' });
  assert.deepEqual(unconfigured.calls, []);
  const failing = fixture({ configure: async () => ({ ok: false, code: 'STATE_CONFLICT',
    runtime: { state: 'unconfigured', model: null } }) });
  assert.deepEqual(await failing.handlers.get('desktop:assistant-model-switch')('allowed'),
    { ok: false, code: 'STATE_CONFLICT', runtime: { state: 'unconfigured', model: null } });
  assert.deepEqual(failing.persisted, []);
  const throwing = fixture({ configure: async () => { throw Error('synthetic'); } });
  assert.deepEqual(await throwing.handlers.get('desktop:assistant-model-switch')('allowed'),
    { ok: false, code: 'BLOCKED_LIVE' });
  const lying = fixture({ configure: async () => ({ ok: true,
    runtime: { state: 'configured', model: 'deepseek-flash' } }) });
  const lied = await lying.handlers.get('desktop:assistant-model-switch')('allowed');
  assert.equal(lied.ok, false, 'a configure that did not apply the requested model never persists');
  assert.deepEqual(lying.persisted, []);
});

test('startup auto-configure restores only a persisted known choice and never throws', async () => {
  const calls = [];
  const runtime = { configure: async model => { calls.push(model); return { ok: true }; } };
  assert.equal(await autoConfigureModel({ settings: {}, runtime }), false);
  assert.equal(await autoConfigureModel({ settings: { model: 'other' }, runtime }), false);
  assert.equal(await autoConfigureModel({ settings: null, runtime }), false);
  assert.equal(await autoConfigureModel({ settings: { model: 'deepseek-v4-pro' }, runtime: null }), false);
  assert.deepEqual(calls, []);
  assert.equal(await autoConfigureModel({ settings: { model: 'deepseek-v4-pro' }, runtime }), true);
  assert.deepEqual(calls, ['deepseek-v4-pro']);
  const failing = { configure: async () => ({ ok: false, code: 'BLOCKED_LIVE' }) };
  assert.equal(await autoConfigureModel({ settings: { model: 'deepseek-flash' }, runtime: failing }), false);
  const throwing = { configure: async () => { throw Error('synthetic'); } };
  assert.equal(await autoConfigureModel({ settings: { model: 'deepseek-flash' }, runtime: throwing }), false);
});
