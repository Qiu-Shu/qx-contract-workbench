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

test('assistant model switch forwards an explicit off and stops the runtime if saving fails',async()=>{
  const handlers=new Map(),calls=[];
  const runtime={status:()=>({ok:true,runtime:{state:'configured',model:'deepseek-flash'}}),
    async configure(model,guard,automatic){calls.push([model,automatic]);
      return {ok:true,runtime:{state:'configured',model}};},
    async disable(){calls.push('disable');return {ok:true};}};
  registerAssistantModelBridge({ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},runtime,
    isAllowed:()=>true,persist:(model,automatic)=>{calls.push(['save',model,automatic]);return false;}});
  assert.deepEqual(await handlers.get('desktop:assistant-model-switch')({}),{ok:false,code:'BLOCKED_LIVE'});
  assert.deepEqual(calls,[['deepseek-v4-pro',false],['save','deepseek-v4-pro',false],'disable']);
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


test('shared Jev restoration uses saved provider credential and preserves an explicit disable',async()=>{
  const {autoConfigureJudge}=require('../model-bridge.cjs');const calls=[];
  const store={status:async()=>({status:'saved'})},runtime={configure:async model=>{calls.push(model);return {ok:true};}};
  assert.equal(await autoConfigureJudge({settings:{},store,runtime}),true);
  assert.equal(await autoConfigureJudge({settings:{judge_model:false},store,runtime}),false);
  assert.equal(await autoConfigureJudge({settings:{judge_model:'foreign'},store,runtime}),false);
  assert.equal(await autoConfigureJudge({settings:{},store:{status:async()=>({status:'empty'})},runtime}),false);
  assert.deepEqual(calls,['jev-1.13.0']);
  assert.equal(await autoConfigureJudge({settings:{},store,runtime:{configure:async()=>({ok:false})}}),false);
});
