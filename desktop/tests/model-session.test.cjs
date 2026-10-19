const {test}=require('node:test');
const assert=require('node:assert/strict');
const {registerModelSettings}=require('../model-settings.cjs');
const SECRET='SYNTHETIC_NATIVE_SETTINGS_SECRET_20261019';
const VERSION='11111111-2222-4333-8444-555555555555';
const configured=()=>({ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:VERSION});
const disabled=()=>({ok:true,status:'disabled'});
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));

function sessionFixture() {
  const {createModelSession}=require('../model-session.cjs');
  const calls=[],failures=[];
  let payload;
  const backend={control:{ready:true,enabled:true,failed:false,closed:false},closing:false,
    async disableModel(){calls.push('disable');return disabled();},
    async configureModel(value){calls.push('configure');payload=value;return configured();},
    async stop(){calls.push('stop');this.closing=true;},
    async authorizeModel(){assert.fail('settings must never authorize sending');}};
  let current=backend;
  const store={async withSecret(consumer){calls.push('consume');
    try{await consumer(SECRET);return {status:'saved'};}
    catch{return {status:'unavailable',code:'CREDENTIAL_STORAGE_FAILED'};}}};
  const session=createModelSession({store,getBackend:()=>current,onFailure:async value=>failures.push(value)});
  return {session,backend,store,calls,failures,get payload(){return payload;},setBackend(value){current=value;}};
}

function brokerFixture(runtime) {
  const handlers=new Map(),calls=[];
  let busy=false,epoch=1;
  const event={document:1};
  const store={async status(){calls.push('status');return {status:'empty'};},
    async save(){calls.push('save');return {status:'saved'};},
    async remove(){calls.push('remove');return {status:'empty'};},async drain(){}};
  const broker=registerModelSettings({ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},store,runtime,
    isAllowed:value=>value===event && !busy,
    captureGuard:()=>{const captured=epoch;return ()=>captured===epoch;},
    setBusy:value=>{busy=value;}});
  return {handlers,calls,event,store,broker,get busy(){return busy;},navigate(){epoch++;},
    call:(name,...args)=>handlers.get('desktop:model-'+name)(event,...args)};
}

test('credential writes revoke current runtime before touching the protected store',async()=>{
  const events=[];
  const f=brokerFixture({async beforeCredentialChange(){events.push('disable');return {ok:true,
    runtime:{state:'unconfigured',model:null}};}});
  f.store.save=async()=>{events.push('save');return {status:'saved'};};
  assert.deepEqual(await f.call('save',SECRET),{status:'saved'});
  assert.deepEqual(events,['disable','save']);
});

test('trusted model selection configures only the fixed catalog and never grants sending',async()=>{
  const f=sessionFixture();
  assert.deepEqual(f.session.status(),{ok:true,runtime:{state:'unconfigured',model:null}});
  assert.deepEqual(await f.session.configure('deepseek-flash'),
    {ok:true,runtime:{state:'configured',model:'deepseek-flash'}});
  assert.deepEqual(f.calls,['disable','consume','configure']);
  assert.equal(f.payload.secret===SECRET,true);
  assert.equal(f.payload.config.model,'deepseek-flash');
  assert.equal(f.payload.config.input_usd_per_million,'0.3');
  assert.equal(f.payload.config.output_usd_per_million,'1.2');
});

test('second model uses bounded trusted configuration and projections omit private metadata',async()=>{
  const f=sessionFixture();
  const result=await f.session.configure('deepseek-v4-pro');
  assert.deepEqual(result,{ok:true,runtime:{state:'configured',model:'deepseek-v4-pro'}});
  assert.deepEqual(f.payload.config,{enabled:true,protocol_version:'deepseek-chat-json-v1',
    provider:'deepseek',model:'deepseek-v4-pro',max_input_bytes:65536,max_output_tokens:4096,
    max_response_bytes:1048576,timeout_seconds:30,input_usd_per_million:'1.32',
    output_usd_per_million:'3.96',
    price_reference:'https://api-docs.deepseek.com/quick_start/pricing/ (2026-10-19; peak/cache-miss; USD)'});
  assert.deepEqual(f.session.status(),result);
  assert.deepEqual(f.calls,['disable','consume','configure']);
});

test('arbitrary configuration is refused without consuming credentials and clears prior configuration',async()=>{
  const f=sessionFixture();
  await f.session.configure('deepseek-flash');f.calls.length=0;
  assert.deepEqual(await f.session.configure({model:'deepseek-flash',endpoint:'https://invalid.test'}),
    {ok:false,code:'BLOCKED_LIVE',runtime:{state:'unconfigured',model:null}});
  assert.deepEqual(f.calls,['disable']);
});

test('credential read failure cannot preserve a prior configured model',async()=>{
  const f=sessionFixture();
  await f.session.configure('deepseek-flash');f.calls.length=0;
  f.store.withSecret=async()=>({status:'unavailable',code:'CREDENTIAL_ROTATION_REQUIRED'});
  assert.deepEqual(await f.session.configure('deepseek-v4-pro'),
    {ok:false,code:'CREDENTIAL_ROTATION_REQUIRED',runtime:{state:'unconfigured',model:null}});
  assert.deepEqual(f.calls,['disable']);
});

test('consumer completion does not turn a rejected configuration ACK into success',async()=>{
  const f=sessionFixture();
  f.backend.configureModel=async()=>({ok:false,code:'VERSION_CONFLICT'});
  assert.deepEqual(await f.session.configure('deepseek-flash'),
    {ok:false,code:'VERSION_CONFLICT',runtime:{state:'unconfigured',model:null}});
  assert.deepEqual(f.calls,['disable','consume']);
});

test('malformed success ACK closes the captured backend and never exposes its extra fields',async()=>{
  const f=sessionFixture();
  f.backend.configureModel=async()=>({...configured(),private_value:SECRET});
  const result=await f.session.configure('deepseek-flash');
  assert.deepEqual(result,{ok:false,code:'BLOCKED_LIVE',runtime:{state:'unavailable',model:null}});
  assert.deepEqual(f.calls,['disable','consume','stop']);
  assert.deepEqual(f.failures,[f.backend]);
});

test('health failure arriving with a valid ACK prevents configuration adoption',async()=>{
  const f=sessionFixture();
  f.backend.configureModel=async()=>{f.backend.control.failed=true;return configured();};
  const result=await f.session.configure('deepseek-flash');
  assert.equal(result.ok,false);
  assert.deepEqual(result.runtime,{state:'unavailable',model:null});
  assert.deepEqual(f.calls,['disable','consume','stop']);
});

test('backend replacement while reading the credential prevents its handoff',async()=>{
  const f=sessionFixture(),gate=deferred();
  f.store.withSecret=async consumer=>{await gate.promise;await consumer(SECRET);return {status:'saved'};};
  const pending=f.session.configure('deepseek-flash');await tick();
  const replacement=sessionFixture().backend;f.setBackend(replacement);gate.resolve();
  assert.deepEqual(await pending,{ok:false,code:'STATE_CONFLICT',runtime:{state:'unconfigured',model:null}});
  assert.deepEqual(f.calls,['disable']);
});

test('late configuration ACK stops only the old backend after process replacement',async()=>{
  const f=sessionFixture(),gate=deferred(),replacement=sessionFixture();
  f.backend.configureModel=async()=>gate.promise;
  const pending=f.session.configure('deepseek-flash');await tick();
  f.setBackend(replacement.backend);gate.resolve(configured());
  assert.deepEqual(await pending,{ok:false,code:'STATE_CONFLICT',runtime:{state:'unconfigured',model:null}});
  assert.deepEqual(f.calls,['disable','consume','stop']);
  assert.deepEqual(replacement.calls,[]);
});

test('an obsolete document cannot adopt an ACK or invoke page failure handling',async()=>{
  const f=sessionFixture(),gate=deferred();let current=true;
  f.backend.configureModel=async()=>gate.promise;
  const pending=f.session.configure('deepseek-flash',()=>current);await tick();
  current=false;gate.resolve(configured());
  assert.equal((await pending).ok,false);
  assert.deepEqual(f.calls,['disable','consume','stop']);
  assert.deepEqual(f.failures,[]);
});

test('runtime operations refuse overlapping mutations instead of queuing them',async()=>{
  const f=sessionFixture(),gate=deferred();
  f.backend.configureModel=async()=>gate.promise;
  const pending=f.session.configure('deepseek-flash');await tick();
  assert.deepEqual(f.session.status().runtime,{state:'unavailable',model:null});
  assert.equal((await f.session.disable()).code,'STATE_CONFLICT');
  assert.equal((await f.session.configure('deepseek-v4-pro')).code,'STATE_CONFLICT');
  assert.deepEqual(f.calls,['disable','consume']);
  gate.resolve(configured());assert.equal((await pending).ok,true);
});

test('failed revocation waits for backend stop and forbids the credential write',async()=>{
  const f=sessionFixture(),gate=deferred(),broker=brokerFixture(f.session);
  f.backend.disableModel=async()=>({ok:false,code:'BLOCKED_LIVE'});
  f.backend.stop=async()=>{f.calls.push('stop');await gate.promise;f.backend.closing=true;};
  let settled=false;
  const pending=broker.call('save',SECRET).then(result=>{settled=true;return result;});
  await tick();assert.equal(settled,false);assert.equal(broker.busy,true);
  assert.deepEqual(broker.calls,[]);
  let drained=false;const wait=broker.broker.wait().then(()=>{drained=true;});
  await tick();assert.equal(drained,false);
  gate.resolve();
  assert.deepEqual(await pending,{status:'unavailable',code:'CREDENTIAL_STORAGE_FAILED'});
  await wait;assert.deepEqual(broker.calls,[]);assert.equal(broker.busy,false);
});

test('a failed backend stop latches unsafe state even after the backend reference is cleared',async()=>{
  const f=sessionFixture();
  f.backend.disableModel=async()=>{throw new Error('synthetic control failure');};
  f.backend.stop=async()=>{throw new Error('synthetic stop failure');};
  assert.equal((await f.session.beforeCredentialChange()).ok,false);
  f.setBackend(null);
  assert.equal((await f.session.beforeCredentialChange()).ok,false);
  assert.deepEqual(f.session.status().runtime,{state:'unavailable',model:null});
});

test('credential and runtime IPC share a busy lock while the captured document guard remains valid',async()=>{
  const gate=deferred(),broker=brokerFixture({async configure(){return gate.promise;}});
  const pending=broker.call('configure','deepseek-flash');await tick();
  assert.deepEqual(await broker.call('save',SECRET),{status:'unavailable',code:'ACCESS_DENIED'});
  assert.deepEqual(await broker.call('status'),{status:'unavailable',code:'ACCESS_DENIED'});
  assert.equal((await broker.call('disable')).code,'ACCESS_DENIED');
  assert.deepEqual(broker.calls,[]);
  gate.resolve({ok:true,runtime:{state:'configured',model:'deepseek-flash'},
    config_version:VERSION,config_sha256:'a'.repeat(64),private_value:SECRET});
  assert.deepEqual(await pending,{ok:true,runtime:{state:'configured',model:'deepseek-flash'}});
  assert.equal(broker.busy,false);
});

test('document epoch is rechecked after revocation before any credential write',async()=>{
  const gate=deferred(),broker=brokerFixture({async beforeCredentialChange(){return gate.promise;}});
  const pending=broker.call('remove');await tick();broker.navigate();
  gate.resolve({ok:true,runtime:{state:'unconfigured',model:null}});
  assert.deepEqual(await pending,{status:'unavailable',code:'ACCESS_DENIED'});
  assert.deepEqual(broker.calls,[]);
});

test('navigation before IPC work starts prevents all runtime and credential work',async()=>{
  let calls=0;
  const broker=brokerFixture({async configure(){calls++;return {ok:true,runtime:{state:'configured',model:'deepseek-flash'}};}});
  const pending=broker.call('configure','deepseek-flash');broker.navigate();
  assert.equal((await pending).code,'ACCESS_DENIED');
  assert.equal(calls,0);assert.deepEqual(broker.calls,[]);
});

test('runtime status neither consumes credentials nor preserves metadata across backend replacement',async()=>{
  const f=sessionFixture();
  await f.session.configure('deepseek-flash');f.calls.length=0;
  assert.equal(f.session.status().runtime.state,'configured');
  f.setBackend(sessionFixture().backend);
  assert.deepEqual(f.session.status().runtime,{state:'unconfigured',model:null});
  f.setBackend(null);
  assert.deepEqual(f.session.status().runtime,{state:'unavailable',model:null});
  assert.deepEqual(f.calls,[]);
});
