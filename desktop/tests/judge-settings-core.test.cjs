const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ModelControl}=require('../model-control.cjs');
const {createModelSession}=require('../model-session.cjs');
const {registerModelSettings}=require('../model-settings.cjs');
const protocol='qx-model-control-v1',judgeProtocol='qx-judge-control-v1';
const nonce='a'.repeat(32),version='11111111-2222-4333-8444-555555555555';
const secret='SYNTHETIC_JUDGE_SETTINGS_NOT_A_REAL_KEY';
const frame=x=>Buffer.from(JSON.stringify(x)+'\n');
const ack=status=>({ok:true,status,...(status==='configured'?{config_sha256:'a'.repeat(64),config_version:version}:{})});
function pipe(t,extra={judge_control_protocol:judgeProtocol}) {
  const writes=[],fatal=[];
  const control=new ModelControl({nonce,write:x=>writes.push(JSON.parse(x)),onReady(){},onFatal:x=>fatal.push(x)});
  t.after(()=>control.close());
  control.feed(frame({event:'ready',port:18001,nonce,control_protocol:protocol,...extra}));
  return {control,writes,fatal,answer(status){control.feed(frame({event:'model-control-result',protocol,nonce,sequence:control.sequence,...ack(status)}));}};
}
function fixture() {
  const calls=[];
  const backend={control:{ready:true,enabled:true,judgeEnabled:true},closing:false,
    async configureJudge(value){calls.push(['configureJudge',value]);return ack('configured');},
    async disableJudge(){calls.push(['disableJudge']);return ack('disabled');},
    async configureModel(){assert.fail('judge must not configure main');},
    async disableModel(){assert.fail('judge must not disable main');},
    async stop(){this.closing=true;calls.push(['stop']);}};
  const store={async withSecret(fn){calls.push(['secret']);await fn(secret);return {status:'saved'};}};
  let current=backend;
  const runtime=createModelSession({kind:'judge',store,getBackend:()=>current});
  return {runtime,backend,store,calls,setBackend:value=>{current=value;}};
}
test('judge capability negotiates on the existing pipe and shares the sequence',async t=>{
  const f=pipe(t);assert.equal(f.control.judgeEnabled,true);assert.deepEqual(f.fatal,[]);
  const p=f.control.request('configure_judge',{config:{enabled:true,model:'jev-1.13.0'},secret});
  assert.equal(f.writes[0].operation,'configure_judge');f.answer('configured');assert.equal((await p).status,'configured');
  const q=f.control.request('disable',{});assert.equal(f.writes[1].sequence,2);f.answer('disabled');await q;
});
test('legacy main capability cannot send judge frames or consume sequence',async t=>{
  const f=pipe(t,{});assert.deepEqual(await f.control.request('disable_judge',{}),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(f.writes.length,0);assert.equal(f.control.sequence,0);
  const p=f.control.request('disable',{});f.answer('disabled');assert.equal((await p).status,'disabled');
});
test('unknown judge protocol is fatal before readiness',t=>{const f=pipe(t,{judge_control_protocol:'unknown'});assert.equal(f.fatal.length,1);assert.equal(f.control.ready,false);});
test('judge configure uses fixed trusted model without authorization or main calls',async()=>{
  const f=fixture();assert.equal(f.runtime.status().runtime.state,'unconfigured');
  assert.equal((await f.runtime.configure('jev-1.13.0')).ok,true);
  assert.equal(f.runtime.withAuthorization,undefined);
  assert.deepEqual(f.calls.map(x=>x[0]),['disableJudge','secret','configureJudge']);
  assert.deepEqual(f.calls[2][1],{secret,config:{enabled:true,protocol_version:'typesafe-systemone-v1',model:'jev-1.13.0',max_input_bytes:65536,max_response_bytes:262144,timeout_ms:2000}});
  assert.deepEqual(f.runtime.status(),{ok:true,runtime:{state:'configured',model:'jev-1.13.0'}});
});
test('judge refuses another provider model without reading a secret',async()=>{
  const f=fixture();assert.equal((await f.runtime.configure('deepseek-flash')).ok,false);
  assert.deepEqual(f.calls.map(x=>x[0]),['disableJudge']);
});
test('judge credential replacement clears configuration before reading a failed new secret',async()=>{
  const f=fixture();await f.runtime.configure('jev-1.13.0');f.calls.length=0;
  f.store.withSecret=async()=>({status:'invalid',code:'CREDENTIAL_CORRUPT'});
  const result=await f.runtime.configure('jev-1.13.0');assert.equal(result.code,'CREDENTIAL_CORRUPT');
  assert.equal(result.runtime.state,'unconfigured');assert.deepEqual(f.calls.map(x=>x[0]),['disableJudge']);
});
test('failed disable closes owned backend before allowing credential edits',async()=>{
  const f=fixture();f.backend.disableJudge=async()=>({ok:false,code:'BLOCKED_LIVE'});
  assert.equal((await f.runtime.beforeCredentialChange()).ok,false);assert.equal(f.backend.closing,true);
});
test('late configuration ack terminates obsolete runtime and never reports configured',async()=>{
  const f=fixture();let valid=true;f.backend.configureJudge=async()=>{valid=false;return ack('configured');};
  const result=await f.runtime.configure('jev-1.13.0',()=>valid);
  assert.equal(result.ok,false);assert.equal(result.runtime.state,'unavailable');assert.equal(f.backend.closing,true);
});
test('backend replacement discards judge status and cannot grant or reuse old state',async()=>{
  const f=fixture();await f.runtime.configure('jev-1.13.0');f.setBackend(null);
  assert.deepEqual(f.runtime.status(),{ok:true,runtime:{state:'unavailable',model:null}});
});
test('old backend is unaffected when storing a future judge credential',async()=>{
  const f=fixture();f.backend.control.judgeEnabled=false;
  assert.equal((await f.runtime.configure('jev-1.13.0')).ok,false);
  assert.equal((await f.runtime.beforeCredentialChange()).ok,true);assert.deepEqual(f.calls,[]);
});
test('judge settings use separate IPC namespace and accept only the judge status model',async()=>{
  const handlers=new Map(),calls=[];let allowed=true;
  const store={async status(){return {status:'saved'};},drain(){}};
  const runtime={status(){return {ok:true,runtime:{state:'configured',model:'jev-1.13.0'},secret};}};
  registerModelSettings({kind:'judge',ipcMain:{handle:(key,fn)=>handlers.set(key,fn)},store,runtime,isAllowed:()=>allowed,setBusy(){}});
  assert.equal(handlers.has('desktop:model-status'),false);assert.equal(handlers.size,6);
  const result=await handlers.get('desktop:judge-runtime-status')({});assert.deepEqual(result,{ok:true,runtime:{state:'configured',model:'jev-1.13.0'}});
  runtime.status=()=>({ok:true,runtime:{state:'configured',model:'deepseek-flash'}});
  assert.equal((await handlers.get('desktop:judge-runtime-status')({})).ok,false);
  allowed=false;assert.equal((await handlers.get('desktop:judge-status')({})).code,'ACCESS_DENIED');
});
test('judge pipe rejects unimplemented grant and malformed disable without writes',async t=>{
  const f=pipe(t);assert.equal((await f.control.request('authorize_judge',{})).ok,false);
  assert.equal((await f.control.request('disable_judge',{secret})).ok,false);assert.equal(f.writes.length,0);
});
