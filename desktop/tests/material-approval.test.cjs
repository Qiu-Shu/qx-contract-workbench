const {test}=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const {createModelSession}=require('../model-session.cjs');
const {registerModelApproval}=require('../model-approval.cjs');

const ID='11111111-2222-4333-8444-555555555555';
const REQUEST='aaaaaaaa-2222-4333-8444-555555555555';
const PARENT='abababab-2222-4333-8444-555555555555';
const TASK='acacacac-2222-4333-8444-555555555555';
const WORKSPACE='bbbbbbbb-2222-4333-8444-555555555555';
const TOKEN='SYNTHETIC_MATERIAL_SESSION_20261026';
const CSRF='SYNTHETIC_MATERIAL_CSRF_20261026';
const scope={workspace_id:WORKSPACE,conversation_id:ID,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:2,materials_revision:1};

function basisFor(input){
  return {request_id:input.request_id,expected_scope:{...input.expected_scope},
    expected_composer_revision:input.expected_composer_revision,parent_business_run_id:PARENT,
    input_format:'material-business-v1',manifest:{input_format:'material-business-v1',workflow:'contract',
      stable_task_id:TASK,parent_business_run_id:PARENT,question:'审查这份独立虚构合同',materials:[{
        attachment_id:ID,name:'虚构合同.docx',original_sha256:'a'.repeat(64),parse_revision:1,
        result_sha256:'b'.repeat(64),reading_status:'readable',pages:[1],parts:['正文'],
        unread_parts:[],quality_issues:[]}],sources:[{source_id:'c'.repeat(64),reference:{kind:'document',
          attachment_id:ID,original_sha256:'a'.repeat(64),parse_revision:1,result_sha256:'b'.repeat(64),
          anchor:{quote:'独立虚构合同原文'}}}]},
    manifest_sha256:'d'.repeat(64),system_sha256:'e'.repeat(64),config_sha256:'f'.repeat(64),
    wire_sha256:'0'.repeat(64),wire_bytes:512};
}

async function fixture(t,automatic=false){
  const input={conversation_id:ID,request_id:REQUEST,expected_scope:{...scope},expected_composer_revision:3,parent_business_run_id:PARENT};
  const draft={scope:{...scope},composer_revision:3,archived_at:null};
  const state={confirm:true,current:true,onConfirm:null,mutatePreview:null,workspace:'synthetic-workspace'};
  const requests=[],calls=[];let details,payload;
  const backend={control:{ready:true,enabled:true,failed:false,closed:false},closing:false,
    async configureModel(){return {ok:true,status:'configured',config_sha256:'f'.repeat(64),config_version:ID};},
    async disableModel(){return {ok:true,status:'disabled'};},
    async authorizeModel(){throw new Error('material flow must not use plain-text authorization');},
    async authorizeMaterialModel(value){calls.push('authorize');payload=value;return {ok:true,status:'authorized'};},
    async revokeModel(){calls.push('revoke');return {ok:true,status:'revoked'};},
    async stop(){this.closing=true;}};
  const runtime=createModelSession({store:{async withSecret(fn){await fn('synthetic_key');return {status:'saved'};}},
    getBackend:()=>backend,getWorkspace:()=>state.workspace});
  await runtime.configure('deepseek-flash',()=>true,automatic);
  const server=http.createServer((req,res)=>{
    const item={method:req.method,path:req.url,cookie:req.headers.cookie,csrf:req.headers['x-csrf-token']};requests.push(item);
    res.setHeader('Content-Type','application/json');
    if(req.url.endsWith('/material-preview')){
      let raw='';req.on('data',chunk=>raw+=chunk);return req.on('end',()=>{
        item.body=JSON.parse(raw);let basis=basisFor(input);
        if(state.mutatePreview)basis=state.mutatePreview(basis,requests.filter(x=>x.method==='POST').length);
        res.end(JSON.stringify(basis));
      });
    }
    res.end(JSON.stringify(draft));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve);}));
  const origin='http://127.0.0.1:'+server.address().port,event={},handlers=new Map();
  const session={cookies:{async get(){return [{name:'qx_session',value:TOKEN},{name:'qx_csrf',value:CSRF}];}}};
  const context={origin,session,parent:{},backend,conversation_id:ID,guard:()=>state.current};
  registerModelApproval({ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},runtime,
    captureContext:value=>value===event?context:null,isBusy:()=>false,setBusy:()=>{},
    async confirm(value){details=value.details;calls.push('confirm');return state.onConfirm?state.onConfirm(value):state.confirm;}});
  const invoke=(value=input)=>handlers.get('desktop:approve-material')(event,value);
  return {input,state,requests,calls,runtime,backend,details:()=>details,payload:()=>payload,invoke};
}

test('explicit automatic material analysis skips confirmation but keeps both snapshots and bounded lease',async t=>{
  const f=await fixture(t,true);f.state.confirm=false;
  assert.deepEqual(await f.invoke(),{ok:true});
  assert.deepEqual(f.calls,['authorize']);
  assert.equal(f.requests.filter(value=>value.method==='POST').length,2);
  assert.equal(f.payload().max_total_usd,'0.024576');
  assert.equal(f.payload().expected_config_version,ID);
});

const history=()=>[
  {message_id:'cccccccc-2222-4333-8444-555555555555',role:'user',source_revision:1,content:'前次问题：虚构合同约定哪一天付款？'},
  {message_id:'dddddddd-2222-4333-8444-555555555555',role:'assistant',source_revision:1,content:'前次待核回答：请核对附件日期。'}
];
test('automatic material analysis authorizes the exact same-task history from both snapshots',async t=>{
  const f=await fixture(t,true);
  f.state.mutatePreview=basis=>({...basis,manifest:{...basis.manifest,conversation_history:history()}});
  assert.deepEqual(await f.invoke(),{ok:true});
  assert.deepEqual(f.calls,['authorize']);
  assert.deepEqual(f.payload().basis.manifest.conversation_history,history());
  assert.equal(f.requests.filter(value=>value.method==='POST').length,2);
});

test('automatic material analysis refuses a changed prior answer between snapshots',async t=>{
  const f=await fixture(t,true);
  f.state.mutatePreview=(basis,count)=>{
    const previous=history();if(count>1)previous[1].content='被替换的历史回答';
    return {...basis,manifest:{...basis.manifest,conversation_history:previous}};
  };
  assert.equal((await f.invoke()).ok,false);
  assert.deepEqual(f.calls,[]);assert.equal(f.payload(),undefined);
});

test('automatic analysis still blocks changed basis, cancellation and unknown acknowledgements',async t=>{
  const changed=await fixture(t,true);
  changed.state.mutatePreview=(basis,count)=>count===1?basis:{...basis,wire_sha256:'1'.repeat(64)};
  assert.equal((await changed.invoke()).ok,false);assert.deepEqual(changed.calls,[]);
  const canceled=await fixture(t,true);canceled.state.current=false;
  assert.equal((await canceled.invoke()).ok,false);assert.deepEqual(canceled.calls,[]);
  const unknown=await fixture(t,true);unknown.backend.authorizeMaterialModel=async()=>({ok:true,status:'unknown'});
  assert.equal((await unknown.invoke()).ok,false);assert.equal(unknown.backend.closing,true);
});

test('model, credential, workspace and disable changes invalidate automatic material analysis',async t=>{
  const changed=await fixture(t,true);await changed.runtime.configure('deepseek-v4-pro');
  assert.equal((await changed.invoke()).ok,true);assert.deepEqual(changed.calls,['confirm','authorize']);
  for(const action of ['beforeCredentialChange','disable','workspace']){
    const f=await fixture(t,true);
    if(action==='workspace')f.state.workspace='another-workspace';else await f.runtime[action]();
    assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,[]);
  }
});

test('material confirmation presents exact sources and authorizes the same server basis once',async t=>{
  const f=await fixture(t);
  assert.equal(require('../material-basis.cjs').validMaterialBasis(basisFor(f.input)),true);
  assert.deepEqual(await f.invoke(),{ok:true});
  assert.deepEqual(f.calls,['confirm','authorize']);
  assert.equal(f.details().kind,'material_business');
  assert.equal(f.details().content,'审查这份独立虚构合同');
  assert.equal(f.details().model,'deepseek-flash');
  assert.equal(f.details().recipient,'DeepSeek（api.deepseek.com）');
  assert.deepEqual(f.details().basis,basisFor(f.input));
  assert.deepEqual(f.payload().basis,basisFor(f.input));
  assert.equal(f.payload().session_token,TOKEN);assert.equal(f.payload().valid_for_seconds,120);
  const posts=f.requests.filter(x=>x.method==='POST');assert.equal(posts.length,2);
  for(const post of posts){
    assert.equal(post.cookie,'qx_session='+TOKEN+'; qx_csrf='+CSRF);assert.equal(post.csrf,CSRF);
    assert.deepEqual(post.body,{request_id:REQUEST,expected_scope:scope,expected_composer_revision:3,parent_business_run_id:PARENT});
  }
});

test('cancellation or changed material basis never authorizes a send',async t=>{
  const f=await fixture(t);f.state.confirm=false;
  assert.deepEqual(await f.invoke(),{ok:false,code:'APPROVAL_CANCELED',canceled:true});
  assert.equal(f.payload(),undefined);
  const g=await fixture(t);g.state.mutatePreview=(basis,count)=>count===1?basis:
    {...basis,manifest:{...basis.manifest,question:'确认后被替换的问题'}};
  assert.equal((await g.invoke()).ok,false);assert.equal(g.payload(),undefined);
  assert.deepEqual(g.calls,['confirm']);
});

test('renderer-supplied credentials, budgets, attachments and extra fields are rejected before cookies',async t=>{
  const f=await fixture(t);
  for(const change of [{secret:'forged'},{max_total_usd:'999'},{attachment_ids:[]},{basis:basisFor(f.input)},{extra:true}]){
    assert.deepEqual(await f.invoke({...f.input,...change}),{ok:false,code:'BLOCKED_LIVE'});
  }
  assert.deepEqual(f.calls,[]);assert.deepEqual(f.requests,[]);
});
