import assert from 'node:assert/strict';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';

const copy = value => structuredClone(value);
const failure = (status = 0, code = 'NETWORK_ERROR') => Object.assign(new Error(code), {status, code});
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
};
const tick = () => new Promise(resolve => setImmediate(resolve));
function snapshot(id = 'one', text = '', revision = 0, extras = {}) {
  return {
    scope: {workspace_id: 'workspace', conversation_id: id, scope_kind: 'conversation',
      scope_ref: null, binding_revision: 1, input_revision: 0, materials_revision: 0},
    draft_input: text, composer_revision: revision, messages: [], next_before: null,
    latest_run: null, ...extras,
  };
}
function fixture(initial = snapshot()) {
  let remote = copy(initial), sequence = 0;
  const calls = [], changed = [], identities = [];
  const api = {
    async createConversation(body) { calls.push(['create', copy(body)]); return copy(remote); },
    async getConversation(id, before) { calls.push(['get', id, before]); return copy(remote); },
    async saveDraft(id, body) {
      calls.push(['save', id, copy(body)]);
      remote = {...remote, draft_input: body.content, composer_revision: remote.composer_revision + 1};
      return copy(remote);
    },
    async cancelRun(id, body) { calls.push(['cancel', id, copy(body)]); remote.latest_run.state = 'cancelled'; },
  };
  const controller = createDraftController(api, {
    uuid: () => `request-${++sequence}`,
    onChange: state => changed.push({...state}), onConversation: id => identities.push(id),
  });
  return {api, controller, calls, changed, identities,
    get remote() { return remote; }, set remote(value) { remote = copy(value); }};
}

let passed = 0;
async function check(name, run) {
  await run(); passed += 1; console.log(`PASS ${name}`);
}

await check('archive current returns to fresh chat and retains another chat', async()=>{
  const f=fixture(),c=f.controller;
  f.api.deleteConversation=async(id,body)=>{f.calls.push(['archive',id,copy(body)]);return {...copy(f.remote),archived_at:'2026-10-30T00:00:00Z'};};
  await c.open('one');assert.equal(await c.archiveConversation(c.state.view),true);
  assert.equal(c.state.id,null);assert.equal(c.state.text,'');assert.equal(c.canLeave(),true);
  await c.open('one');const before=c.state.view;
  f.api.deleteConversation=async(id)=>({...snapshot(id),archived_at:'2026-10-30T00:00:00Z'});
  assert.equal(await c.archiveConversation(snapshot('two')),true);
  assert.equal(c.state.id,'one');assert.equal(c.state.view,before);
});
await check('archive blocks dirty text and unfinished work without clearing it',async()=>{
  const f=fixture(),c=f.controller;let calls=0;f.api.deleteConversation=async()=>{calls++;};
  await c.open('one');c.edit('未保存');assert.equal(await c.archiveConversation(c.state.view),false);
  assert.equal(c.state.text,'未保存');assert.equal(calls,0);
  await c.save();c.state.generation.phase='unknown';assert.equal(await c.archiveConversation(c.state.view),false);
  assert.equal(calls,0);
});
await check('archive acknowledgement cannot discard typing or navigation started while pending',async()=>{
  const f=fixture(),c=f.controller,gate=deferred();await c.open('one');
  f.api.deleteConversation=()=>gate.promise;const deleting=c.archiveConversation(c.state.view);await tick();
  assert.equal(c.state.loading,true);c.edit('不能写入将被归档的会话');
  assert.equal(await c.open('two'),false);assert.equal(await c.newConversation(),false);
  assert.equal(c.state.text,'');gate.resolve({...snapshot(),archived_at:'2026-10-30T00:00:00Z'});
  assert.equal(await deleting,true);assert.equal(c.state.id,null);
});
await check('unknown archive keeps exact body and blocks work until idempotent reconciliation',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');const bodies=[];
  f.api.deleteConversation=async(id,body)=>{bodies.push(copy(body));if(bodies.length===1)throw failure(0,'NETWORK_UNKNOWN');
    return {...snapshot(id),archived_at:'2026-10-30T00:00:00Z'};};
  const view=c.state.view;assert.equal(await c.archiveConversation(view),false);
  assert.equal(c.state.archivePending.id,'one');assert.equal(c.canLeave(),false);
  c.edit('不能改写未知结果');assert.equal(c.state.text,'');assert.equal(await c.newConversation(),false);
  assert.equal(await c.archiveConversation(view),true);assert.deepEqual(bodies[0],bodies[1]);
  assert.equal(c.state.id,null);assert.equal(c.state.archivePending,null);
});

await check('blank and skill selection do not create records; read-only never writes', async () => {
  const f = fixture(), c = f.controller;
  c.edit('  \n'); c.selectSkill('contract_review');
  assert.equal(await c.save(), true); assert.equal(f.calls.length, 0);
  assert.equal(c.state.skill, 'contract_review'); assert.equal(c.canLeave(), true);
  const locked = createDraftController(f.api, {readonly: true});
  await locked.open('one'); locked.edit('must not write'); locked.selectSkill('client_reply');
  assert.equal(await locked.save(), true); assert.equal(await locked.cancel(), false);
  assert.equal(locked.state.text, ''); assert.equal(f.calls.filter(x => x[0] !== 'get').length, 0);
});

await check('single save channel preserves input typed during an older acknowledgement', async () => {
  const f = fixture(), c = f.controller;
  await c.open('one'); c.edit('first');
  const first = deferred(), second = deferred(), bodies = [];
  f.api.saveDraft = async (id, body) => {
    bodies.push(copy(body)); return bodies.length === 1 ? first.promise : second.promise;
  };
  const saving = c.save(); await tick();
  c.edit('second'); const joined = c.save();
  assert.equal(c.canLeave(), false); assert.equal(bodies.length, 1);
  first.resolve(snapshot('one', 'first', 1)); await tick();
  assert.equal(c.state.text, 'second'); assert.equal(c.state.savedText, 'first');
  assert.equal(bodies.length, 2); assert.equal(bodies[1].expected_composer_revision, 1);
  second.resolve(snapshot('one', 'second', 2));
  assert.equal(await saving, true); assert.equal(await joined, true);
  assert.equal(c.state.dirty, false); assert.equal(c.canLeave(), true);
});

await check('unknown creation requires explicit retry and preserves its original request identity', async () => {
  const f = fixture(), c = f.controller, bodies = [];
  f.api.createConversation = async body => {
    bodies.push(copy(body)); if (bodies.length === 1) throw failure(); return snapshot();
  };
  c.edit('draft'); assert.equal(await c.save(), false);
  c.edit('latest'); assert.equal(await c.save(), false);
  assert.equal(await c.newConversation(), false); assert.equal(bodies.length, 1);
  assert.equal(c.canLeave(), false); assert.equal(await c.retry(), true);
  assert.deepEqual(bodies[0], bodies[1]); assert.equal(c.state.text, 'latest');
  assert.equal(c.state.savedText, 'latest'); assert.equal(c.state.id, 'one');
});

await check('unknown write is reconciled by exact scope, revision and content before newer input saves', async () => {
  const f = fixture(), c = f.controller; await c.open('one');
  let attempts = 0;
  const normalSave = f.api.saveDraft;
  f.api.saveDraft = async (id, body) => {
    attempts += 1; const result = await normalSave(id, body);
    if (attempts === 1) throw failure(); return result;
  };
  c.edit('committed but response lost'); assert.equal(await c.save(), false);
  c.edit('newer input'); assert.equal(await c.save(), false); assert.equal(attempts, 1);
  assert.equal(await c.retry(), true); assert.equal(attempts, 2);
  assert.equal(c.state.savedText, 'newer input'); assert.equal(c.state.view.composer_revision, 2);
});

await check('unknown write not committed can replay only after unchanged baseline is read', async () => {
  const f = fixture(), c = f.controller; await c.open('one');
  const bodies = [], normalSave = f.api.saveDraft;
  f.api.saveDraft = async (id, body) => {
    bodies.push(copy(body)); if (bodies.length === 1) throw failure(); return normalSave(id, body);
  };
  c.edit('pending'); assert.equal(await c.save(), false); assert.equal(await c.retry(), true);
  assert.deepEqual(bodies[0], bodies[1]); assert.equal(c.state.savedText, 'pending');
});

for (const kind of ['scope', 'revision', 'content']) {
  await check(`unknown write ${kind} mismatch retains both drafts until explicit choice`, async () => {
    const f = fixture(), c = f.controller; await c.open('one');
    f.api.saveDraft = async () => { throw failure(); };
    c.edit('local'); assert.equal(await c.save(), false);
    f.remote = snapshot('one', kind === 'content' ? 'remote' : 'local', kind === 'revision' ? 2 : 1);
    if (kind === 'scope') f.remote.scope.binding_revision = 2;
    assert.equal(await c.retry(), false); assert.equal(c.state.status, 'conflict');
    assert.equal(c.state.text, 'local'); assert.equal(c.state.conflict.server, f.remote.draft_input);
    assert.equal(await c.open('two'), false); assert.equal(c.canLeave(), false);
    assert.equal(await c.resolveConflict('server'), true);
    assert.equal(c.state.text, f.remote.draft_input); assert.equal(c.state.dirty, false);
  });
}

await check('version conflict allows explicitly keeping local text against the new server version', async () => {
  const f = fixture(), c = f.controller; await c.open('one');
  const save = f.api.saveDraft; let count = 0;
  f.api.saveDraft = async (id, body) => {
    if (++count === 1) { f.remote = snapshot('one', 'remote', 4); throw failure(409, 'VERSION_CONFLICT'); }
    return save(id, body);
  };
  c.edit('mine'); assert.equal(await c.save(), false);
  assert.equal(c.state.conflict.local, 'mine'); assert.equal(c.state.conflict.server, 'remote');
  c.edit('mine amended');
  assert.equal(await c.resolveConflict('local'), true);
  assert.equal(c.state.savedText, 'mine amended'); assert.equal(c.state.view.composer_revision, 5);
});

await check('refresh never overwrites unsaved input and detects independent remote edits', async () => {
  const f = fixture(snapshot('one', 'baseline', 2)), c = f.controller;
  await c.open('one'); const read = deferred(); f.api.getConversation = () => read.promise;
  const refreshing = c.refresh(); c.edit('typed while reading');
  read.resolve(snapshot('one', 'baseline', 2)); assert.equal(await refreshing, true);
  assert.equal(c.state.text, 'typed while reading'); assert.equal(c.state.dirty, true);
  f.api.getConversation = async () => snapshot('one', 'remote', 3);
  assert.equal(await c.refresh(), false); assert.equal(c.state.text, 'typed while reading');
  assert.equal(c.state.conflict.server, 'remote');
});

await check('switch waits for save and rejects switching after failed persistence', async () => {
  const f = fixture(), c = f.controller; await c.open('one'); c.edit('pending');
  const write = deferred(); f.api.saveDraft = () => write.promise;
  f.api.getConversation = async id => snapshot(id);
  const switching = c.open('two'); await tick(); assert.equal(c.state.id, 'one');
  write.resolve(snapshot('one', 'pending', 1)); assert.equal(await switching, true);
  assert.equal(c.state.id, 'two'); assert.equal(c.state.text, '');
  c.edit('do not lose'); f.api.saveDraft = async () => { throw failure(); };
  assert.equal(await c.open('three'), false); assert.equal(c.state.id, 'two');
  assert.equal(c.state.text, 'do not lose');
});

await check('late page reads and revocation cannot contaminate a newer conversation', async () => {
  const f = fixture(), c = f.controller, first = deferred(), second = deferred();
  f.api.getConversation = id => id === 'one' ? first.promise : second.promise;
  const one = c.open('one'); await tick(); c.edit('blocked during load');
  assert.equal(c.state.text, ''); assert.equal(c.canLeave(), false);
  const two = c.open('two'); await tick(); second.resolve(snapshot('two', 'new conversation', 2));
  assert.equal(await two, true); first.reject(failure(403, 'CROSS_MATTER_DENIED'));
  assert.equal(await one, false); assert.equal(c.state.id, 'two');
  assert.equal(c.state.text, 'new conversation');
});

await check('current permission revocation clears text, history, skill and identity immediately', async () => {
  const f = fixture(snapshot('one', 'private', 1, {messages: [{id: 'm', content: 'private'}]}));
  const c = f.controller; await c.open('one'); c.edit('private edit'); c.selectSkill('client_reply');
  f.api.getConversation = async () => { throw failure(401, 'AUTH_REQUIRED'); };
  assert.equal(await c.refresh(), false); assert.equal(c.state.id, null);
  assert.equal(c.state.view, null); assert.equal(c.state.text, ''); assert.equal(c.state.skill, null);
  assert.equal(c.state.status, 'revoked'); assert.equal(c.canLeave(), true);
});

await check('older pages deduplicate in chronological order and preserve pending input', async () => {
  const f = fixture(snapshot('one', 'baseline', 1, {
    messages: [{id: '3'}, {id: '4'}], next_before: '3',
  })), c = f.controller; await c.open('one'); c.edit('pending');
  f.api.getConversation = async (id, before) => {
    assert.equal(before, '3'); return snapshot('one', 'remote', 8, {
      messages: [{id: '1'}, {id: '2'}, {id: '3'}], next_before: null,
    });
  };
  assert.equal(await c.loadEarlier(), true);
  assert.deepEqual(c.state.view.messages.map(x => x.id), ['1', '2', '3', '4']);
  assert.equal(c.state.text, 'pending'); assert.equal(c.state.savedText, 'baseline');
  assert.equal(c.state.view.composer_revision, 1); assert.equal(c.state.view.next_before, null);
});

await check('empty page with a cursor can keep paging; refresh retains already loaded history', async () => {
  const f = fixture(snapshot('one', '', 0, {messages: [], next_before: 'cursor'})), c = f.controller;
  await c.open('one'); f.api.getConversation = async () => snapshot('one', '', 0, {messages: [{id: '1'}]});
  assert.equal(await c.loadEarlier(), true);
  f.api.getConversation = async () => snapshot('one', '', 0, {messages: [{id: '1'}, {id: '2'}], next_before: '1'});
  assert.equal(await c.refresh(), true);
  assert.deepEqual(c.state.view.messages.map(x => x.id), ['1', '2']);
  assert.equal(c.state.view.next_before, null);
});

await check('cancel reads the persisted result and preserves unsaved text', async () => {
  const f = fixture(snapshot('one', 'before', 1, {latest_run: {id: 'run', state: 'queued'}}));
  const c = f.controller; await c.open('one'); c.edit('unsaved');
  assert.equal(await c.cancel(), true); assert.equal(c.state.view.latest_run.state, 'cancelled');
  assert.equal(c.state.text, 'unsaved'); assert.equal(c.state.dirty, true);
  assert.equal(f.calls.filter(x => x[0] === 'save').length, 0);
});

await check('close discards delayed replies and removes in-memory content', async () => {
  const f = fixture(), c = f.controller; await c.open('one'); c.edit('pending');
  const write = deferred(); f.api.saveDraft = () => write.promise;
  const saving = c.save(); await tick(); c.close(); write.resolve(snapshot('one', 'pending', 1));
  assert.equal(await saving, false); assert.equal(c.state.view, null); assert.equal(c.state.text, '');
  assert.equal(await c.open('one'), false);
});

await check('unknown write stays dirty even when the user edits back to the saved baseline', async () => {
  const f = fixture(snapshot('one', 'baseline', 1)), c = f.controller;
  await c.open('one'); f.api.saveDraft = async () => { throw failure(); };
  c.edit('unknown'); assert.equal(await c.save(), false); c.edit('baseline');
  assert.equal(c.state.dirty, true); assert.equal(c.canLeave(), false);
});

await check('create replay cannot silently overwrite a draft edited in another window', async () => {
  const f = fixture(), c = f.controller; let calls = 0;
  f.api.createConversation = async () => {
    if (++calls === 1) throw failure(); return snapshot('one', 'other window', 2);
  };
  c.edit('my pending draft'); assert.equal(await c.save(), false);
  assert.equal(await c.retry(), false); assert.equal(c.state.conflict.server, 'other window');
  assert.equal(c.state.text, 'my pending draft'); assert.equal(f.calls.length, 0);
});

await check('a late refresh cannot roll back a completed newer save', async () => {
  const f = fixture(snapshot('one', 'old', 1)), c = f.controller;
  await c.open('one'); const read = deferred(); f.api.getConversation = () => read.promise;
  const refreshing = c.refresh(); c.edit('new'); assert.equal(await c.save(), true);
  read.resolve(snapshot('one', 'old', 1)); assert.equal(await refreshing, false);
  assert.equal(c.state.text, 'new'); assert.equal(c.state.savedText, 'new');
  assert.equal(c.state.view.composer_revision, 2);
});

await check('disjoint refreshed history starts its own cursor instead of hiding unread messages', async () => {
  const f = fixture(snapshot('one', '', 0, {messages: [{id: '1'}], next_before: null})), c = f.controller;
  await c.open('one');
  f.api.getConversation = async () => snapshot('one', '', 0, {messages: [{id: '90'}], next_before: '90'});
  assert.equal(await c.refresh(), true); assert.equal(c.state.view.next_before, '90');
  assert.deepEqual(c.state.view.messages.map(x => x.id), ['90']);
});

await check('an older read finishing does not release the busy guard on a newer read', async () => {
  const f = fixture(), c = f.controller; await c.open('one');
  const oldRead = deferred(), newRead = deferred();
  f.api.getConversation = (id, before) => id === 'one' ? oldRead.promise : snapshot('two');
  const old = c.refresh(); assert.equal(await c.open('two'), true);
  f.api.getConversation = () => newRead.promise;
  const newer = c.refresh(); oldRead.resolve(snapshot()); await old;
  assert.equal(c.canLeave(), false); newRead.resolve(snapshot('two')); await newer;
  assert.equal(c.canLeave(), true);
});

await check('a failed page read leaves no old identity available for accidental draft saves', async () => {
  const f = fixture(), c = f.controller; await c.open('one');
  f.api.getConversation = async () => { throw failure(); };
  assert.equal(await c.open('two'), false); assert.equal(c.state.id, null);
  assert.equal(c.state.view, null); assert.equal(await c.save(), true);
  assert.equal(c.canLeave(), true);
});

await check('late create response after close cannot change identity or notify the page', async () => {
  const f = fixture(), c = f.controller, response = deferred();
  f.api.createConversation = () => response.promise;
  c.edit('pending'); const saving = c.save(); await tick(); c.close();
  const notifications = f.changed.length, identities = f.identities.length;
  response.resolve(snapshot()); assert.equal(await saving, false);
  assert.equal(f.changed.length, notifications); assert.equal(f.identities.length, identities);
});

await check('replayed PUT racing the original can recognize the original successful write', async () => {
  const f = fixture(), c = f.controller; await c.open('one'); let attempts = 0;
  f.api.saveDraft = async (id, body) => {
    if (++attempts === 1) throw failure();
    f.remote = snapshot('one', body.content, 1);
    throw failure(409, 'VERSION_CONFLICT');
  };
  c.edit('same request'); assert.equal(await c.save(), false);
  assert.equal(await c.retry(), true); assert.equal(c.state.dirty, false);
  assert.equal(c.state.conflict, null); assert.equal(c.state.savedText, 'same request');
});

for (const status of [401, 403]) {
  await check(`external ${status} revocation clears unknown writes and rejects delayed reconciliation`, async () => {
    const f = fixture(snapshot('one', 'saved private text', 1, {messages: [{id: 'private-message'}]}));
    const c = f.controller; await c.open('one'); c.selectSkill('contract_review'); c.edit('private edit');
    f.api.saveDraft = async () => { throw failure(); };
    assert.equal(await c.save(), false); assert.equal(c.state.dirty, true);
    const read = deferred(); f.api.getConversation = () => read.promise;
    const retrying = c.retry(); await tick();
    c.revoke(failure(status, status === 401 ? 'AUTHORIZATION_REQUIRED' : 'CROSS_MATTER_DENIED'));
    assert.equal(c.state.status, 'revoked'); assert.equal(c.state.error.status, status);
    assert.equal(c.state.id, null); assert.equal(c.state.view, null); assert.equal(c.state.text, '');
    assert.equal(c.state.savedText, ''); assert.equal(c.state.skill, null); assert.equal(c.state.dirty, false);
    const notifications = f.changed.length, identities = f.identities.length;
    read.resolve(snapshot('one', 'private edit', 2)); assert.equal(await retrying, false);
    assert.equal(f.changed.length, notifications); assert.equal(f.identities.length, identities);
    assert.equal(c.state.view, null); assert.equal(c.state.text, '');
    assert.equal(await c.retry(), false); assert.equal(c.canLeave(), true);
  });
}

await check('external non-authorization errors cannot clear conversation data', async () => {
  const f = fixture(snapshot('one', 'saved', 1, {messages: [{id: 'message'}]})), c = f.controller;
  await c.open('one'); c.edit('unsaved'); c.selectSkill('client_reply');
  for (const status of [0, 400, 404, 409, 422, 500]) assert.equal(c.revoke(failure(status)), false);
  assert.equal(c.state.id, 'one'); assert.equal(c.state.text, 'unsaved');
  assert.equal(c.state.savedText, 'saved'); assert.equal(c.state.skill, 'client_reply');
  assert.deepEqual(c.state.view.messages, [{id: 'message'}]); assert.equal(c.state.error, null);
});

console.log(`${passed} assistant state checks passed`);
