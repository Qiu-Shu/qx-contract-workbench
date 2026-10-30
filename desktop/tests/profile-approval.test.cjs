const {test}=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {createHash}=require('node:crypto');
const {createModelSession}=require('../model-session.cjs');
const {registerModelApproval}=require('../model-approval.cjs');

const ID='11111111-2222-4333-8444-555555555555';
const REQUEST='aaaaaaaa-2222-4333-8444-555555555555';
const WORKSPACE='bbbbbbbb-2222-4333-8444-555555555555';
const INTAKE='cccccccc-2222-4333-8444-555555555555';
const TOKEN='SYNTHETIC_PROFILE_SESSION_20261023';
const CSRF='SYNTHETIC_PROFILE_CSRF_20261023';
const CONTENT='仅用于本机测试的虚构来访情况。\n 本行空白和完整文字需要保留。';
const digest=value=>createHash('sha256').update(value,'utf8').digest('hex');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};

function basisFor(input,content=CONTENT) {
  return {input_format:'profile-text-v1',template_version:'profile-text-system-v1',
    purpose:'reply_and_profile_draft',handler_id:'profile.save',handler_version:'1',
    request_id:input.request_id,expected_scope:{...input.expected_scope},
    expected_composer_revision:input.expected_composer_revision,content_sha256:digest(content),
    base_profile_revision:0,expected_intake_id:null,expected_intake_revision:null,
    project_intake:input.project_intake,system_sha256:'a'.repeat(64),config_sha256:'b'.repeat(64),
    wire_sha256:'c'.repeat(64),wire_bytes:512};
}

async function fixture(t,options={}) {
  const scope={workspace_id:WORKSPACE,conversation_id:ID,scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:0};
  const input={conversation_id:ID,request_id:REQUEST,expected_scope:{...scope},
    expected_composer_revision:1,project_intake:false};
  const draft={scope:{...scope},draft_input:CONTENT,composer_revision:1,archived_at:null,latest_run:null};
  const materials={scope:{...scope},items:[],attachments:[]};
  const requests=[],calls=[],cookieReads=[];
  let payload,details;
  const state={current:true,confirmResult:true,betweenSnapshots:null,onAuthorize:null,mutatePreview:null,respond:null};
  const backend={control:{ready:true,enabled:true,failed:false,closed:false},closing:false,
    async configureModel(){return {ok:true,status:'configured',config_sha256:'b'.repeat(64),config_version:ID};},
    async disableModel(){return {ok:true,status:'disabled'};},
    async authorizeModel(){calls.push('authorize-plain');return {ok:true,status:'authorized'};},
    async authorizeProfileModel(value){calls.push('authorize-profile');payload=value;
      return state.onAuthorize?state.onAuthorize(value):{ok:true,status:'authorized'};},
    async revokeModel(value){calls.push('revoke');state.revoked=value;return {ok:true,status:'revoked'};},
    async stop(){calls.push('stop');this.closing=true;}};
  const cookies=[{name:'qx_session',value:TOKEN},{name:'qx_csrf',value:CSRF}];
  const session={cookies:{async get(value){cookieReads.push(value.url);return cookies;}}};
  const runtime=createModelSession({store:{async withSecret(fn){await fn('synthetic_key');return {status:'saved'};}},
    getBackend:()=>backend});
  await runtime.configure('deepseek-flash');
  const server=http.createServer((req,res)=>{
    const item={path:req.url,method:req.method,cookie:req.headers.cookie,csrf:req.headers['x-csrf-token']};
    requests.push(item);
    if(state.respond && state.respond(req,res))return;
    res.setHeader('Content-Type','application/json');
    if(req.url.endsWith('/materials'))return res.end(JSON.stringify(materials));
    if(req.url.endsWith('/profile-preview') && req.method==='POST'){
      let raw='';req.on('data',chunk=>raw+=chunk);
      return req.on('end',()=>{
        item.body=JSON.parse(raw);
        let basis=basisFor(item.body,draft.draft_input);
        if(state.mutatePreview)basis=state.mutatePreview(basis,requests.filter(value=>value.method==='POST').length);
        res.end(JSON.stringify(basis));
      });
    }
    res.end(JSON.stringify(draft));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve);}));
  const origin='http://127.0.0.1:'+server.address().port;
  const event={},parent={},handlers=new Map();let busy=false;
  const context={origin,session,parent,backend,conversation_id:ID,guard:()=>state.current};
  const registration=registerModelApproval({ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},runtime,
    judgeRuntime:options.judgeRuntime,
    captureContext:value=>value===event?{...context}:null,isBusy:()=>busy,setBusy:value=>{busy=value;},
    async confirm(){throw new Error('ordinary sends must not open a confirmation window');}});
  const invoke=async (value=input,sender=event)=>{
      const previous=session.cookies.get,baseline=requests.length;let crossed=false;
      session.cookies.get=async(...args)=>{
        if(!crossed&&requests.length>=baseline+3){crossed=true;calls.push('boundary');if(state.betweenSnapshots)await state.betweenSnapshots();}
        return previous(...args);
      };
      try{return await handlers.get('desktop:approve-profile')(sender,value);}
      finally{session.cookies.get=previous;}
    };
  return {scope,input,draft,materials,requests,calls,cookieReads,cookies,state,backend,session,runtime,context,registration,
    invoke,invokeChannel:(name,value=input)=>handlers.get(name)(event,value),
    get payload(){return payload;},get details(){return details;},get busy(){return busy;}};
}

test('profile IPC uses trusted saved text, direct basis, fixed cost and native authorized status',async t=>{
  const f=await fixture(t,{judgeRuntime:{withAuthorization(){throw new Error('profile must not authorize Jev');}}});
  assert.deepEqual(await f.invoke(),{ok:true,status:'authorized'});
  assert.deepEqual(f.calls,['boundary','authorize-profile']);
  assert.deepEqual(f.payload,{session_token:TOKEN,expected_config_version:ID,basis:basisFor(f.input),
    max_total_usd:'0.024576',valid_for_seconds:120});
  assert.equal(f.requests.length,6);
  for(const post of f.requests.filter(value=>value.method==='POST')){
    assert.ok(post.path.endsWith('/profile-preview'));
    assert.equal(post.cookie,'qx_session='+TOKEN+'; qx_csrf='+CSRF);assert.equal(post.csrf,CSRF);
    assert.deepEqual(post.body,{request_id:REQUEST,expected_scope:f.scope,expected_composer_revision:1,project_intake:false});
  }
  assert.ok(f.cookieReads.some(url=>url.endsWith('/profile-preview')));
});

test('existing receipt remains distinguishable and never creates a second grant',async t=>{
  const f=await fixture(t);f.state.onAuthorize=()=>({ok:true,status:'existing'});
  assert.deepEqual(await f.invoke(),{ok:true,status:'existing'});
  assert.deepEqual(f.calls,['boundary','authorize-profile']);
});

test('profile send uses configured scope without a per-send dialog',async t=>{
  const f=await fixture(t);f.state.confirmResult=false;
  assert.deepEqual(await f.invoke(),{ok:true,status:'authorized'});
  assert.deepEqual(f.calls,['boundary','authorize-profile']);
});

test('strict five selection fields reject renderer bytes, budgets, skills, attachments and malformed scope',async t=>{
  const f=await fixture(t);
  const bad=[{content:'forged'},{basis:basisFor(f.input)},{max_total_usd:'1'},{model:'forged'},
    {requested_skill:'contract_review'},{attachment_ids:[]},{project_intake:0},{project_intake:'false'},
    {request_id:'bad'},{expected_composer_revision:true},{expected_composer_revision:1.5},
    {expected_composer_revision:-1},{expected_scope:{...f.scope,extra:true}},
    {expected_scope:{...f.scope,binding_revision:0}},{expected_scope:{...f.scope,workspace_id:'bad'}},
    {expected_scope:{...f.scope,scope_kind:'conversation',scope_ref:INTAKE}}];
  for(const change of bad)assert.deepEqual(await f.invoke({...f.input,...change}),{ok:false,code:'BLOCKED_LIVE'});
  const missing={...f.input};delete missing.project_intake;
  assert.deepEqual(await f.invoke(missing),{ok:false,code:'BLOCKED_LIVE'});
  assert.deepEqual(f.calls,[]);assert.deepEqual(f.requests,[]);assert.deepEqual(f.cookieReads,[]);
});

test('profile IPC rejects a foreign sender, conversation and non-owned origin before cookie reads',async t=>{
  const f=await fixture(t);
  assert.deepEqual(await f.invoke(f.input,{}),{ok:false,code:'ACCESS_DENIED'});
  assert.deepEqual(await f.invoke({...f.input,conversation_id:WORKSPACE,
    expected_scope:{...f.scope,conversation_id:WORKSPACE}}),{ok:false,code:'ACCESS_DENIED'});
  for(const origin of ['http://localhost:1234','http://127.0.0.1:12/extra','http://127.0.0.1:65536',
    'https://127.0.0.1:1234','http://127.0.0.1:1@invalid.test']){
    f.context.origin=origin;assert.deepEqual(await f.invoke(),{ok:false,code:'ACCESS_DENIED'});
  }
  assert.deepEqual(f.cookieReads,[]);assert.deepEqual(f.requests,[]);
});

for(const location of ['draft','materials','basis'])test('profile checks every scope field in '+location,async t=>{
  const f=await fixture(t);
  for(const [key,value] of [['workspace_id',REQUEST],['conversation_id',REQUEST],['scope_kind','intake'],
    ['scope_ref',INTAKE],['binding_revision',2],['input_revision',1],['materials_revision',1],['extra',true]]){
    if(location==='basis')f.state.mutatePreview=basis=>({...basis,expected_scope:{...basis.expected_scope,[key]:value}});
    else f[location].scope={...f.scope,[key]:value};
    assert.equal((await f.invoke()).ok,false,key);
  }
  assert.deepEqual(f.calls,[]);
});

test('only a current nonblank text-only draft with no active run can be approved',async t=>{
  const f=await fixture(t);
  for(const change of [()=>{f.draft.archived_at='2026-10-23T00:00:00Z';},()=>{f.draft.composer_revision=2;},
    ()=>{f.draft.draft_input=' ';},()=>{f.draft.draft_input='文'.repeat(22000);},
    ()=>{f.materials.items=[{attachment_id:INTAKE}];},()=>{f.materials.attachments=[{id:INTAKE}];},
    ()=>{delete f.materials.attachments;},()=>{f.draft.latest_run={state:'unknown'};},
    ...['queued','preparing','routing','retrieving','generating','persisting','awaiting_input'].map(state=>()=>{f.draft.latest_run={state};})]){
    change();assert.equal((await f.invoke()).ok,false);
    Object.assign(f.draft,{archived_at:null,composer_revision:1,draft_input:CONTENT,latest_run:null});
    Object.assign(f.materials,{items:[],attachments:[]});
  }
  assert.deepEqual(f.calls,[]);
});

for(const [key,value] of Object.entries({input_format:'plain-text-v1',template_version:'wrong',purpose:'chat',
  handler_id:'other.save',handler_version:'2',request_id:INTAKE,expected_composer_revision:2,
  content_sha256:'e'.repeat(64),base_profile_revision:1,expected_intake_id:INTAKE,expected_intake_revision:1,
  project_intake:true,system_sha256:'d'.repeat(64),config_sha256:'d'.repeat(64),wire_sha256:'d'.repeat(64),wire_bytes:513})){
  test('changing profile basis '+key+' between snapshots prevents authorization',async t=>{
    const f=await fixture(t);f.state.mutatePreview=(basis,count)=>count===1?basis:{...basis,[key]:value};
    assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,['boundary']);
  });
}

test('a reordered but identical complete basis remains valid and does not mutate native details',async t=>{
  const f=await fixture(t);f.state.mutatePreview=(basis,count)=>count===1?basis:
    Object.fromEntries(Object.entries({...basis,expected_scope:Object.fromEntries(Object.entries(basis.expected_scope).reverse())}).reverse());
  assert.deepEqual(await f.invoke(),{ok:true,status:'authorized'});
});

test('direct preview rejects legacy wrappers, missing and additional basis fields',async t=>{
  const f=await fixture(t);
  for(const mutate of [basis=>({state:'ready',send_basis:basis}),basis=>({...basis,extra:true}),basis=>{
    delete basis.wire_sha256;return basis;},basis=>({...basis,project_intake:'false'})]){
    f.state.mutatePreview=mutate;assert.deepEqual(await f.invoke(),{ok:false,code:'BLOCKED_LIVE'});
  }
  assert.deepEqual(f.calls,[]);
});

test('existing intake target and its revision are authorized exactly',async t=>{
  const f=await fixture(t);f.input.project_intake=true;
  f.state.mutatePreview=basis=>({...basis,base_profile_revision:4,expected_intake_id:INTAKE,expected_intake_revision:7});
  assert.deepEqual(await f.invoke(),{ok:true,status:'authorized'});
  assert.equal(f.payload.basis.project_intake,true);assert.equal(f.payload.basis.expected_intake_id,INTAKE);
  assert.equal(f.payload.basis.expected_intake_revision,7);assert.equal(f.payload.basis.base_profile_revision,4);
});

test('saved text or materials changed between snapshots cannot be authorized',async t=>{
  const f=await fixture(t);
  for(const change of [()=>{f.draft.draft_input+='新字';},()=>{f.materials.attachments.push({id:INTAKE});},
    ()=>{f.draft.latest_run={state:'generating'};}]){
    f.state.betweenSnapshots=async()=>{change();return true;};assert.equal((await f.invoke()).ok,false);
    f.draft.draft_input=CONTENT;f.materials.attachments=[];f.draft.latest_run=null;
  }
  assert.equal(f.calls.includes('authorize-profile'),false);
});

test('a valid changed intake identity and revision between snapshots also prevent authorization',async t=>{
  const f=await fixture(t);f.input.project_intake=true;
  f.state.mutatePreview=(basis,count)=>({...basis,expected_intake_id:count===1?INTAKE:WORKSPACE,
    expected_intake_revision:count===1?2:3});
  assert.deepEqual(await f.invoke(),{ok:false,code:'STATE_CONFLICT'});
  assert.deepEqual(f.calls,['boundary']);
});

test('renderer or confirmation-detail mutation cannot change the captured profile selection',async t=>{
  const f=await fixture(t);f.state.betweenSnapshots=()=>{
    f.input.project_intake=true;f.input.expected_scope.input_revision=5;
    return true;
  };
  assert.deepEqual(await f.invoke(),{ok:true,status:'authorized'});
  assert.equal(f.payload.basis.project_intake,false);assert.equal(f.payload.basis.expected_scope.input_revision,0);
  assert.equal(f.payload.basis.base_profile_revision,0);
});

test('completed historical skill work does not impersonate a current profile skill selection',async t=>{
  const f=await fixture(t);f.draft.latest_run={state:'completed',requested_skill:'client_reply'};
  assert.deepEqual(await f.invoke(),{ok:true,status:'authorized'});
  for(const post of f.requests.filter(request=>request.method==='POST'))assert.equal('requested_skill' in post.body,false);
});

test('missing or ambiguous CSRF and endpoint-specific session cookies fail closed',async t=>{
  const f=await fixture(t);
  for(const values of [[{name:'qx_session',value:TOKEN}],
    [...f.cookies,{name:'qx_csrf',value:CSRF}], [...f.cookies,{name:'qx_session',value:TOKEN}]]){
    f.session.cookies.get=async()=>values;assert.equal((await f.invoke()).ok,false);
  }
  f.session.cookies.get=async({url})=>[{name:'qx_session',value:url.endsWith('/profile-preview')?'other':TOKEN},
    {name:'qx_csrf',value:CSRF}];
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,[]);assert.deepEqual(f.requests,[]);
});

test('cookie replacement between snapshots is denied before native authorization',async t=>{
  const f=await fixture(t);f.state.betweenSnapshots=()=>{f.cookies[0].value='replacement';return true;};
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,['boundary']);
});

for(const status of ['authorized','existing'])test('late cookie replacement cleans up only a new '+status+' grant',async t=>{
  const f=await fixture(t);f.state.onAuthorize=()=>{f.cookies[0].value='replacement';return {ok:true,status};};
  assert.equal((await f.invoke()).ok,false);
  assert.deepEqual(f.calls,['boundary','authorize-profile',...(status==='authorized'?['revoke']:[])]);
  if(status==='authorized')assert.deepEqual(f.state.revoked,{session_token:TOKEN});
});

test('profile shares pending, busy, wait and runtime lock with both older IPC channels',async t=>{
  const f=await fixture(t),gate=deferred();f.state.betweenSnapshots=()=>gate.promise;
  const pending=f.invoke();while(!f.calls.includes('boundary'))await tick();
  assert.deepEqual(await f.invoke(),{ok:false,code:'STATE_CONFLICT'});
  for(const channel of ['desktop:approve-generation','desktop:approve-context'])
    assert.deepEqual(await f.invokeChannel(channel),{ok:false,code:'STATE_CONFLICT'});
  assert.equal((await f.runtime.configure('deepseek-v4-pro')).code,'STATE_CONFLICT');
  let settled=false;const wait=f.registration.wait().then(()=>{settled=true;});await tick();
  assert.equal(settled,false);assert.equal(f.busy,true);
  gate.resolve();assert.equal((await pending).ok,true);await wait;assert.equal(f.busy,false);
});

for(const key of ['parent','session','backend','origin','conversation_id'])test('replaced '+key+' identity invalidates profile consent',async t=>{
  const f=await fixture(t);f.state.betweenSnapshots=()=>{f.context[key]={};return true;};
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,['boundary']);
});

test('invalidated document guard prevents profile consent',async t=>{
  const f=await fixture(t);f.state.betweenSnapshots=()=>{f.state.current=false;return true;};
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,['boundary']);
});

test('unknown or malformed native ACK never becomes a successful profile status',async t=>{
  for(const ack of [{ok:true},{ok:true,status:'configured'},{ok:true,status:'existing',extra:true},{ok:false,code:'private text'}]){
    const f=await fixture(t);f.state.onAuthorize=()=>ack;
    assert.deepEqual(await f.invoke(),{ok:false,code:'STATE_CONFLICT'});
    assert.ok(f.calls.includes('stop'),'an invalid ACK terminates the owned backend');
  }
});

test('HTTP redirects, malformed JSON and excessive or invalid UTF8 bodies produce only fixed errors',async t=>{
  const f=await fixture(t);
  for(const respond of [
    (_req,res)=>{res.writeHead(302,{Location:'http://invalid.test/'});res.end();return true;},
    (_req,res)=>{res.setHeader('Content-Type','application/json');res.end('private bad json');return true;},
    (_req,res)=>{res.setHeader('Content-Type','application/json');res.end(' '.repeat(262145));return true;},
    (_req,res)=>{res.setHeader('Content-Type','application/json');res.end(Buffer.from([0xff]));return true;}
  ]){f.state.respond=respond;assert.deepEqual(await f.invoke(),{ok:false,code:'BLOCKED_LIVE'});}
  assert.deepEqual(f.calls,[]);assert.equal(f.busy,false);
});

test('preload exposes a frozen profile selector on the dedicated approval channel',()=>{
  const exposed={},calls=[];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../preload.cjs'),'utf8'),{require:()=>({
    contextBridge:{exposeInMainWorld:(name,value)=>{exposed[name]=value;}},
    ipcRenderer:{invoke:(...args)=>calls.push(args),on(){}}
  })});
  assert.equal(Object.isFrozen(exposed.desktopAssistant),true);
  assert.equal(typeof exposed.desktopAssistant.authorizeProfile,'function');
  const input={conversation_id:ID};exposed.desktopAssistant.authorizeProfile(input);
  assert.deepEqual(calls,[['desktop:approve-profile',input]]);
});
