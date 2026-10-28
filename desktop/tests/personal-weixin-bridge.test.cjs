const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createModelSession}=require('../model-session.cjs');
const {registerPersonalWeixin}=require('../personal-weixin.cjs');
const id='11111111-2222-4333-8444-555555555555',other='22222222-2222-4333-8444-555555555555';
const scope={workspace_id:id,conversation_id:id,scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:0,materials_revision:0};
const defer=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve:v=>resolve(v)};};
function fixture(){
  const handlers=new Map(),calls=[];let cid=id,token='FICTIONAL_TOKEN',valid=true,policyVersion=0;
  const backend={control:{personalWeixinEnabled:true},closing:false,
    startPersonalWeixin:async value=>{calls.push(['start',value]);return {ok:true,status:'started'};},
    disablePersonalWeixin:async()=>{calls.push(['disable']);return {ok:true,status:'disabled'};},
    verifyPersonalWeixin:async value=>{calls.push(['verify',value]);return {ok:true,status:'accepted'};},
    stop:async()=>calls.push(['stop'])};
  let server={state:'connected',conversation_id:id,automatic:true,notice:'虚构连接',qr_url:null},statusRead=null;
  const ipcMain={handle:(name,fn)=>handlers.set(name,fn)};
  const bridge=registerPersonalWeixin({ipcMain,runtime:{personalWeixinPolicy(owned,guard){
    const version=policyVersion;return {automatic_policy:{expected_config_version:id,max_total_usd:'0.024576'},
      guard:()=>owned===backend&&guard()&&version===policyVersion};}},
    captureContext:()=>{const captured=cid;return valid?{origin:'http://127.0.0.1:12345',backend,conversation_id:cid,workspace:'main',
      session:{cookies:{get:async()=>[{name:'qx_session',value:token}]}},guard:()=>valid&&cid===captured}:null;},
    readJSON:async(_origin,path,actual)=>{assert.equal(actual,token);calls.push(['read',path]);
      if(path==='/api/session')return {username:'fiction'};
      if(path.endsWith('/status')){if(statusRead)await statusRead;return structuredClone(server);}
      return {scope:{...scope,conversation_id:cid},archived_at:null};}});
  return {bridge,backend,calls,call:(op,value={})=>handlers.get('desktop:personal-weixin-'+op)({},value),
    navigate:()=>{cid=other;},logout:()=>{token='OTHER_TOKEN';},invalidate:()=>{valid=false;},config:()=>{policyVersion++;},
    status:value=>{server={...server,...value};},holdStatus:promise=>{statusRead=promise;}};
}
test('native policy comes from current model metadata, with a version fence',async()=>{
  const backend={configureModel:async()=>({ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:id}),
    disableModel:async()=>({ok:true,status:'disabled'}),stop:async()=>{}};
  const runtime=createModelSession({store:{withSecret:async cb=>{await cb('fictional');return {status:'saved'};}},getBackend:()=>backend,getWorkspace:()=>'/fictional'});
  assert.equal(runtime.personalWeixinPolicy(backend).automatic_policy,null);
  await runtime.configure('deepseek-flash',()=>true,true);
  const captured=runtime.personalWeixinPolicy(backend);
  assert.equal(captured.automatic_policy.expected_config_version,id);assert.equal(captured.guard(),true);
  await runtime.disable();assert.equal(captured.guard(),false);
});
test('start uses native scope, cookie and policy; renderer authority is rejected',async()=>{
  const f=fixture();assert.equal((await f.call('start',{peer:'forged'})).ok,false);
  assert.equal((await f.call('start')).ok,true);
  assert.deepEqual(f.calls.find(x=>x[0]==='start')[1],{session_token:'FICTIONAL_TOKEN',expected_scope:scope,
    automatic_policy:{expected_config_version:id,max_total_usd:'0.024576'}});
  assert.equal((await f.call('start')).ok,false);assert.equal(f.calls.filter(x=>x[0]==='start').length,1);
});
for(const change of ['navigate','logout','config','invalidate'])test('late start ACK disables captured backend after '+change,async()=>{
  const f=fixture(),hold=defer();f.backend.startPersonalWeixin=()=>hold.promise;
  const pending=f.call('start');await new Promise(setImmediate);f[change]();hold.resolve({ok:true,status:'started'});
  assert.equal((await pending).ok,false);assert.ok(f.calls.some(x=>x[0]==='disable'));
});
test('duplicate in-flight start is blocked',async()=>{
  const f=fixture(),hold=defer();f.backend.startPersonalWeixin=()=>hold.promise;
  const pending=f.call('start');assert.equal((await f.call('start')).ok,false);hold.resolve({ok:true,status:'started'});await pending;
});
test('browsing preserves original connection and permits same-session disconnect',async()=>{
  const f=fixture();await f.call('start');f.navigate();
  const result=await f.call('status');assert.equal(result.connection.conversation_id,id);
  assert.equal((await f.call('verify',{code:'001234'})).ok,false);
  assert.equal((await f.call('disable')).ok,true);assert.ok(f.calls.some(x=>x[0]==='disable'));
});
test('navigation during a read-only status query retains the fixed original connection',async()=>{
  const f=fixture();await f.call('start');const hold=defer();f.holdStatus(hold.promise);
  const pending=f.call('status');await new Promise(setImmediate);f.navigate();hold.resolve();
  assert.equal((await pending).ok,false);assert.equal(f.calls.some(x=>x[0]==='disable'),false);
  assert.equal((await f.call('status')).connection.conversation_id,id);
});
test('new login cannot see or retain previous connection',async()=>{
  const f=fixture();await f.call('start');f.logout();
  assert.equal((await f.call('status')).ok,false);assert.ok(f.calls.some(x=>x[0]==='disable'));
});
test('verification preserves leading zeros, rejects extra keys and stale ACK',async()=>{
  const f=fixture();await f.call('start');f.status({state:'need_verifycode'});
  for(const value of [{code:1234},{code:'１２３４'},{code:'1234',peer:id}])assert.equal((await f.call('verify',value)).ok,false);
  const hold=defer();f.backend.verifyPersonalWeixin=value=>{assert.deepEqual(value,{code:'001234'});return hold.promise;};
  const pending=f.call('verify',{code:'001234'});await new Promise(setImmediate);f.navigate();hold.resolve({ok:true,status:'accepted'});
  assert.equal((await pending).ok,false);assert.ok(f.calls.some(x=>x[0]==='disable'));
});
test('QR URL is never returned to renderer IPC and close tears down authority',async()=>{
  const f=fixture();await f.call('start');f.status({state:'waiting_scan',qr_url:'https://fiction.invalid/secret'});
  const result=await f.call('status');assert.equal(result.connection.qr_ready,true);
  assert.equal(JSON.stringify(result).includes('secret'),false);
  await f.bridge.close();assert.ok(f.calls.some(x=>x[0]==='disable'));assert.equal((await f.call('start')).ok,false);
});
test('explicit disconnect waits for an in-flight bounded status read',async()=>{
  const f=fixture();await f.call('start');const hold=defer();
  f.backend.verifyPersonalWeixin=()=>hold.promise;f.status({state:'need_verifycode'});
  const verifying=f.call('verify',{code:'001234'});await new Promise(setImmediate);
  const disabling=f.call('disable');hold.resolve({ok:true,status:'accepted'});
  assert.equal((await verifying).ok,true);assert.equal((await disabling).ok,true);
  assert.ok(f.calls.some(x=>x[0]==='disable'));
});
