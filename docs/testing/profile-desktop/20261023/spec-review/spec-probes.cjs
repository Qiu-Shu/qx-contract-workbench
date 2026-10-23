const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const vm=require('node:vm');
const {createHash}=require('node:crypto');
const root=path.resolve(__dirname,'../../..');
const {createModelSession}=require(path.join(root,'desktop/model-session.cjs'));
const {createProfileSnapshot}=require(path.join(root,'desktop/profile-approval.cjs'));
const {canonicalProfileBasis}=require(path.join(root,'desktop/profile-basis.cjs'));
const ID='68db79ee-6666-4444-8888-111111111111', RID='68db79ee-6666-4444-8888-222222222222';
const TARGET='68db79ee-6666-4444-8888-333333333333', TOKEN='SYNTHETIC_SPEC_TOKEN';
const text='独立合成复核：<img src=x onerror=alert(1)>客户陈述尚未核实。';
const scope={workspace_id:ID,conversation_id:ID,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:0};
const basis=()=>({input_format:'profile-text-v1',template_version:'profile-text-system-v1',
  purpose:'reply_and_profile_draft',handler_id:'profile.save',handler_version:'1',request_id:RID,
  expected_scope:{...scope},expected_composer_revision:1,content_sha256:createHash('sha256').update(text).digest('hex'),
  base_profile_revision:0,expected_intake_id:null,expected_intake_revision:null,project_intake:false,
  system_sha256:'a'.repeat(64),config_sha256:'b'.repeat(64),wire_sha256:'c'.repeat(64),wire_bytes:512});
async function setup(status){
  const calls=[];
  const backend={control:{ready:true,enabled:true,failed:false,closed:false},closing:false,
    async configureModel(){return {ok:true,status:'configured',config_sha256:'b'.repeat(64),config_version:ID};},
    async disableModel(){return {ok:true,status:'disabled'};},
    async authorizeModel(){throw Error('unexpected plain path');},
    async authorizeProfileModel(p){calls.push(['grant',p]);return {ok:true,status};},
    async revokeModel(p){calls.push(['revoke',p]);return {ok:true,status:'revoked'};},
    async stop(){calls.push(['stop']);this.closing=true;}};
  const runtime=createModelSession({store:{withSecret:async fn=>{await fn('SYNTHETIC_SPEC_KEY');return {status:'saved'};}},getBackend:()=>backend});
  assert.equal((await runtime.configure('deepseek-flash')).ok,true);
  return {backend,runtime,calls};
}
for(const status of ['authorized','existing'])test('callback cannot replace trusted '+status+' with opposite status',async()=>{
  const f=await setup(status);
  const result=await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    assert.deepEqual(await lease.authorizeProfile({session_token:TOKEN,basis:basis()}),{ok:true,status});
    return {ok:true,status:status==='authorized'?'existing':'authorized'};
  });
  assert.deepEqual(result,{ok:true,status});assert.deepEqual(f.calls.map(c=>c[0]),['grant']);
});
for(const status of ['authorized','existing'])test('late failure cleans up only authority added by '+status,async()=>{
  const f=await setup(status);
  const result=await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    await lease.authorizeProfile({session_token:TOKEN,basis:basis()});throw Error('synthetic post-check failure');
  });
  assert.equal(result.ok,false);
  assert.deepEqual(f.calls.map(c=>c[0]),status==='authorized'?['grant','revoke']:['grant']);
  if(status==='authorized')assert.deepEqual(f.calls[1][1],{session_token:TOKEN});
});
test('a callback without a native call cannot fabricate profile authority',async()=>{
  const f=await setup('authorized');
  assert.equal((await f.runtime.withAuthorization(f.backend,()=>true,async()=>({ok:true,status:'authorized'}))).ok,false);
  assert.deepEqual(f.calls,[]);
});
function snapshotFixture(){
  const draft={scope:{...scope},composer_revision:1,draft_input:text,archived_at:null,latest_run:null};
  const materials={scope:{...scope},items:[],attachments:[]}, value=basis(),calls=[];
  const read=createProfileSnapshot({check:g=>g(),fail:()=>{throw Error('BLOCKED');},
    tokenFor:async()=>TOKEN,csrfCookie:async()=>TOKEN,
    readJSON:async(_o,p)=>p.endsWith('/materials')?materials:draft,
    postJSON:async(_o,p,_t,_c,body)=>{calls.push({p,body});return structuredClone(value);}});
  const input={conversation_id:ID,request_id:RID,expected_scope:{...scope},expected_composer_revision:1,project_intake:false};
  return {draft,materials,value,calls,read:()=>read({},input,'/api/assistant/conversations/'+ID,()=>true)};
}
test('awaiting-input run rejects before even the deterministic preview POST',async()=>{
  const f=snapshotFixture();f.draft.latest_run={state:'awaiting_input'};
  await assert.rejects(f.read(),/BLOCKED/);assert.deepEqual(f.calls,[]);
});
test('same wire and text with changed valid local target produce unequal complete snapshots',async()=>{
  const f=snapshotFixture(),first=await f.read();
  f.value.expected_intake_id=TARGET;f.value.expected_intake_revision=3;f.value.base_profile_revision=4;
  const second=await f.read();
  assert.equal(first.content,second.content);assert.equal(first.basis.wire_sha256,second.basis.wire_sha256);
  assert.notEqual(first.basisKey,second.basisKey);assert.equal(canonicalProfileBasis(second.basis).expected_intake_id,TARGET);
  assert.equal(f.calls.length,2);assert.ok(f.calls.every(c=>c.p.endsWith('/profile-preview')));
});
async function modal(value){
  const nodes=new Map(),events={};
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{textContent:'',hidden:false,disabled:true,checked:false,
      addEventListener(){},focus(){this.focused=true;},set innerHTML(_v){throw Error('unsafe HTML');}});
    return nodes.get(id);
  };
  vm.runInNewContext(fs.readFileSync(path.join(root,'desktop/model-approval.js'),'utf8'),{
    document:{getElementById:node},window:{desktopApproval:{state:async()=>value,decide:async()=>true},
      addEventListener:(name,fn)=>events[name]=fn}});
  await new Promise(resolve=>setImmediate(resolve));return {node,events};
}
for(const project of [false,true])test('modal shows conditional local intent and only literal text, project='+project,async()=>{
  const value=basis();value.project_intake=project;
  if(!project){value.expected_intake_id=TARGET;value.expected_intake_revision=7;}
  const f=await modal({kind:'profile_draft',content:text,model:'deepseek-flash',max_total_usd:'0.024576',
    recipient:'DeepSeek（api.deepseek.com）',basis:value});
  assert.equal(f.node('approval-confirm').disabled,false);assert.equal(f.node('approval-cancel').focused,true);
  assert.equal(f.node('approval-content').textContent,text);assert.equal(f.node('approval-profile').hidden,false);
  assert.equal(f.node('approval-judge').hidden,true);
  if(project)assert.match(f.node('approval-profile-intake').textContent,/有可用于接待的字段.*尝试创建/);
  else assert.equal(f.node('approval-profile-intake').textContent,'本次不同步接待记录。');
  assert.doesNotMatch(f.node('approval-profile-target').textContent,/已保存|已建档/);
  f.events.pagehide();assert.equal(f.node('approval-content').textContent,'');
});
