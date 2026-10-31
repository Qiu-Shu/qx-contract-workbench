const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ModelControl}=require('../model-control.cjs');
const {Backend}=require('../backend.cjs');
const id='11111111-2222-4333-8444-555555555555',nonce='f'.repeat(32);
const frame=value=>Buffer.from(JSON.stringify(value)+'\n');
function setup(t,capability=true){
  const writes=[],fatal=[];
  const control=new ModelControl({nonce,write:line=>writes.push(line),onReady:()=>{},onFatal:code=>fatal.push(code)});
  t.after(()=>control.close());
  control.feed(frame({event:'ready',port:19022,nonce,control_protocol:'qx-model-control-v1',
    ...(capability?{personal_weixin_protocol:'qx-personal-weixin-v1'}:{})}));
  return {control,writes,fatal};
}
const payload={session_token:'FICTIONAL_TOKEN',expected_scope:{workspace_id:id,conversation_id:id,
  scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:0,materials_revision:0},
  automatic_policy:null};

test('personal automatic policy carries a null main budget through the existing control frame',async t=>{
  const {control,writes}=setup(t);
  const pending=control.request('start_personal_weixin',{...payload,
    automatic_policy:{expected_config_version:id,max_total_usd:null}});
  assert.equal(writes.length,1);
  assert.equal(JSON.parse(writes[0]).payload.automatic_policy.max_total_usd,null);
  control.feed(frame({event:'model-control-result',protocol:'qx-model-control-v1',nonce,
    sequence:1,ok:true,status:'started'}));
  assert.equal((await pending).ok,true);
});
test('legacy backend never receives unknown personal operations',async t=>{
  const {control,writes}=setup(t,false);
  for(const op of ['start_personal_weixin','disable_personal_weixin','verify_personal_weixin'])
    assert.deepEqual(await control.request(op,op==='start_personal_weixin'?payload:{}),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(writes.length,0);
});
for(const [operation,status,value] of [['start_personal_weixin','started',payload],
    ['disable_personal_weixin','disabled',{}],['verify_personal_weixin','accepted',{code:'123456'}]]){
  test(operation+' keeps its acknowledgement status-only',async t=>{
    const {control,writes,fatal}=setup(t);
    const pending=control.request(operation,value);
    assert.equal(JSON.parse(writes[0]).operation,operation);
    control.feed(frame({event:'model-control-result',protocol:'qx-model-control-v1',nonce,sequence:1,ok:true,status}));
    assert.deepEqual(await pending,{ok:true,status});assert.deepEqual(fatal,[]);
  });
}
test('strict personal policy and operation payloads reject renderer-like authority additions',async t=>{
  const {control,writes}=setup(t);
  for(const value of [{...payload,peer:'other'}, {...payload,automatic_policy:{expected_config_version:id,max_total_usd:'Infinity'}},
      {...payload,automatic_policy:{expected_config_version:id,max_total_usd:'1',max_calls:99}},
      {...payload,expected_scope:{...payload.expected_scope,bot:'other'}}])
    assert.deepEqual(await control.request('start_personal_weixin',value),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(writes.length,0);
});
test('backend forwards the three trusted methods to its existing channel',async()=>{
  const backend=new Backend('unused'),calls=[];
  backend.control={request:async(...args)=>{calls.push(args);return {ok:true};}};
  await backend.startPersonalWeixin(payload);await backend.disablePersonalWeixin();await backend.verifyPersonalWeixin({code:'1234'});
  assert.deepEqual(calls.map(x=>x[0]),['start_personal_weixin','disable_personal_weixin','verify_personal_weixin']);
});
