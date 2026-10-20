const test=require('node:test');
const assert=require('node:assert/strict');
const {ModelControl}=require('../model-control.cjs');
const {Backend}=require('../backend.cjs');
const id='00000000-0000-4000-8000-000000000001';
const payload=()=>({session_token:'synthetic-session',expected_config_version:id,
  basis:{request_id:id,expected_scope:{},expected_composer_revision:0,content_sha256:'a'.repeat(64),purpose:'primary_intent'},
  max_total_usd:'0.02',valid_for_seconds:120});
function start(auth=true,judge=true){
  const writes=[],failures=[];
  const control=new ModelControl({nonce:'synthetic-nonce',write:line=>writes.push(JSON.parse(line)),onReady:()=>{},onFatal:code=>failures.push(code)});
  const ready={event:'ready',port:1024,nonce:'synthetic-nonce',control_protocol:'qx-model-control-v1'};
  if(judge)ready.judge_control_protocol='qx-judge-control-v1';
  if(auth)ready.judge_authorization_protocol='qx-judge-authorization-v1';
  control.feed(Buffer.from(JSON.stringify(ready)+'\n'));
  return {control,writes,failures};
}
function ack(control,status){control.feed(Buffer.from(JSON.stringify({event:'model-control-result',protocol:'qx-model-control-v1',nonce:'synthetic-nonce',sequence:control.sequence,ok:true,status})+'\n'));}
test('new capability admits exact Judge authorization and revoke on the same sequence',async()=>{
  const {control,writes,failures}=start();
  assert.equal(control.judgeAuthorizationEnabled,true);assert.deepEqual(failures,[]);
  const pending=control.request('authorize_judge',payload());assert.equal(writes.length,1);
  ack(control,'authorized');assert.deepEqual(await pending,{ok:true,status:'authorized'});
  const revoke=control.request('revoke_judge',{session_token:'synthetic-session'});
  ack(control,'revoked');assert.deepEqual(await revoke,{ok:true,status:'revoked'});
  assert.deepEqual(writes.map(x=>x.sequence),[1,2]);control.close();
});
test('config-only child rejects authorization without writing or stopping existing controls',async()=>{
  const {control,writes,failures}=start(false);
  assert.deepEqual(await control.request('authorize_judge',payload()),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(writes.length,0);assert.deepEqual(failures,[]);assert.equal(control.judgeEnabled,true);
  const disable=control.request('disable_judge',{});ack(control,'disabled');assert.equal((await disable).ok,true);control.close();
});
test('authorization capability without Judge configuration capability fails the handshake',()=>{
  const {control,failures}=start(true,false);assert.equal(control.failed,true);assert.equal(failures.length,1);
});
for(const [name,change] of [
  ['main basis without purpose',v=>delete v.basis.purpose],
  ['different purpose',v=>v.basis.purpose='material_type'],
  ['injected policy',v=>v.policy={}],
  ['numeric budget',v=>v.max_total_usd=.02],
  ['wrong config version',v=>v.expected_config_version='bad'],
  ['unknown scope grant',v=>v.basis.allowed_materials=[]]
])test('Judge authorization refuses '+name,async()=>{
  const {control,writes}=start();const value=payload();change(value);
  assert.deepEqual(await control.request('authorize_judge',value),{ok:false,code:'BLOCKED_LIVE'});assert.equal(writes.length,0);control.close();
});
test('Judge authorization cannot compete with an outstanding Main operation',async()=>{
  const {control,writes}=start();const main=control.request('disable',{});
  assert.deepEqual(await control.request('authorize_judge',payload()),{ok:false,code:'STATE_CONFLICT'});
  assert.equal(writes.length,1);ack(control,'disabled');await main;control.close();
});
test('Backend facade keeps Judge authorization names fixed',async()=>{
  const calls=[],backend={_model:(...args)=>calls.push(args)};
  assert.equal(typeof Backend.prototype.authorizeJudge,'function');assert.equal(typeof Backend.prototype.revokeJudge,'function');
  Backend.prototype.authorizeJudge.call(backend,payload());Backend.prototype.revokeJudge.call(backend,{session_token:'synthetic-session'});
  assert.deepEqual(calls.map(x=>x[0]),['authorize_judge','revoke_judge']);
});
