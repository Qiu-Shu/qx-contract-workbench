const {test}=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const {createHash}=require('node:crypto');
const {createModelSession}=require(require('node:path').resolve('desktop/model-session.cjs'));
const ID='11111111-2222-4333-8444-555555555555';
const REQUEST='aaaaaaaa-2222-4333-8444-555555555555';
const WORKSPACE='bbbbbbbb-2222-4333-8444-555555555555';
const TOKEN='SYNTHETIC_APPROVAL_SESSION_20261019';
const CONTENT='仅用于本机测试的虚构文字。\n第二行保留完整空白。';
const digest=value=>createHash('sha256').update(value,'utf8').digest('hex');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
async function fixture(t) {
  const scope={workspace_id:WORKSPACE,conversation_id:ID,scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:0};
  const input={conversation_id:ID,request_id:REQUEST,expected_scope:{...scope},
    expected_composer_revision:1,content_sha256:digest(CONTENT)};
  const draft={scope:{...scope},draft_input:CONTENT,composer_revision:1,archived_at:null,latest_run:null};
  const capability={scope:{...scope},composer_revision:1,basis:'saved_draft',content_sha256:digest(CONTENT),state:'unapproved'};
  const materials={scope:{...scope},items:[],attachments:[]};
  const requests=[],calls=[],cookies=[];let payload,details;
  const backend={control:{ready:true,enabled:true,failed:false,closed:false},closing:false,
    async configureModel(){return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:ID};},
    async disableModel(){return {ok:true,status:'disabled'};},
    async authorizeModel(value){calls.push('authorize');payload=value;return {ok:true,status:'authorized'};},
    async revokeModel(){calls.push('revoke');return {ok:true,status:'revoked'};},
    async stop(){calls.push('stop');this.closing=true;}};
  const session={cookies:{async get(value){cookies.push(value);return [{name:'qx_session',value:TOKEN},{name:'other',value:'ignored'}];}}};
  const runtime=createModelSession({store:{async withSecret(fn){await fn('synthetic_key');return {status:'saved'};}},getBackend:()=>backend});
  await runtime.configure('deepseek-flash');
  const state={current:true,confirmResult:true,onConfirm:null,respond:null};
  const server=http.createServer((req,res)=>{
    requests.push({path:req.url,method:req.method,cookie:req.headers.cookie});
    if(state.respond && state.respond(req,res))return;
    res.setHeader('Content-Type','application/json');
    res.end(JSON.stringify(req.url.endsWith('/materials')?materials:
      req.url.endsWith('/generation-capability')?capability:draft));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve);}));
  const origin='http://127.0.0.1:'+server.address().port;
  const event={},parent={},handlers=new Map();let busy=false;
  const context={origin,session,parent,backend,conversation_id:ID,guard:()=>state.current};
  const {registerModelApproval}=require(require('node:path').resolve('desktop/model-approval.cjs'));
  const registration=registerModelApproval({ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},runtime,
    captureContext:value=>value===event?{...context}:null,isBusy:()=>busy,setBusy:value=>{busy=value;},
    async confirm(value){details=value.details;calls.push('confirm');
      if(state.onConfirm)return state.onConfirm(value);return state.confirmResult;}});
  return {scope,input,draft,capability,materials,requests,calls,cookies,backend,runtime,session,state,context,
    registration,get payload(){return payload;},get details(){return details;},get busy(){return busy;},
    invoke:(value=input,sender=event)=>handlers.get('desktop:approve-generation')(sender,value)};
}


test('a fresh context with changed parent session backend or origin rejects after confirmation even if its guard stays true',async t=>{
  for(const key of ['parent','session','backend','origin','conversation_id']) {
    const f=await fixture(t),old=f.context[key];
    f.state.onConfirm=async()=>{f.context[key]=key==='origin'?'http://127.0.0.1:1':key==='conversation_id'?WORKSPACE:{};return true;};
    assert.equal((await f.invoke()).ok,false,key);assert.deepEqual(f.calls,['confirm'],key);
    assert.equal(f.requests.length,3,key);f.context[key]=old;
  }
});

test('renderer cannot submit identity text config version or price through native approval input',async t=>{
  const f=await fixture(t);
  for(const extra of [{session_token:TOKEN},{content:CONTENT},{expected_config_version:ID},
    {model:'deepseek-v4-pro'},{max_total_usd:'0.0001'},{provider:'other'},{endpoint:'http://127.0.0.1:1'}])
    assert.equal((await f.invoke({...f.input,...extra})).ok,false);
  assert.deepEqual(f.calls,[]);assert.deepEqual(f.requests,[]);assert.deepEqual(f.cookies,[]);
});

test('caller mutation after dispatch cannot change the captured request or scope',async t=>{
  const f=await fixture(t),gate=deferred();f.state.onConfirm=()=>gate.promise;
  const input=structuredClone(f.input),pending=f.invoke(input);
  while(!f.calls.includes('confirm'))await tick();
  input.request_id=WORKSPACE;input.expected_scope.workspace_id=REQUEST;input.content_sha256='0'.repeat(64);
  gate.resolve(true);assert.equal((await pending).ok,true);
  assert.equal(f.payload.basis.request_id,REQUEST);assert.equal(f.payload.basis.expected_scope.workspace_id,WORKSPACE);
  assert.equal(f.payload.basis.content_sha256,digest(CONTENT));
});

test('empty archived overlimit or digest-mismatched server text never reaches confirmation',async t=>{
  const f=await fixture(t);
  const initial={...f.draft};
  for(const changes of [{draft_input:'   '},{archived_at:'2026-10-19T00:00:00Z'},
    {draft_input:'界'.repeat(21846)},{draft_input:CONTENT+' changed'}]) {
    Object.assign(f.draft,initial,changes);assert.equal((await f.invoke()).ok,false);
  }
  assert.deepEqual(f.calls,[]);
});

test('post-ACK cookie lookup failure awaits revoke and owned shutdown before releasing shared busy',async t=>{
  const f=await fixture(t),gate=deferred();let settled=false;
  const originalCookie=f.session.cookies.get;
  f.backend.authorizeModel=async()=>{f.calls.push('authorize');
    f.session.cookies.get=async()=>{throw Error('PRIVATE_READ_FAILED');};return {ok:true,status:'authorized'};};
  f.backend.revokeModel=async()=>{f.calls.push('revoke');return {ok:false,code:'BLOCKED_LIVE'};};
  f.backend.stop=async()=>{f.calls.push('stop');f.backend.closing=true;await gate.promise;};
  const pending=f.invoke().then(value=>{settled=true;return value;});
  while(!f.calls.includes('stop'))await tick();
  assert.equal(settled,false);assert.equal(f.busy,true);assert.equal((await f.invoke()).code,'STATE_CONFLICT');
  gate.resolve();assert.deepEqual(await pending,{ok:false,code:'BLOCKED_LIVE'});assert.equal(f.busy,false);
  assert.deepEqual(f.calls,['confirm','authorize','revoke','stop']);
  assert.equal(f.runtime.status().runtime.state,'unavailable');f.session.cookies.get=originalCookie;
});

test('late successful authorization after context replacement revokes only its original session',async t=>{
  const f=await fixture(t);let revoked;
  f.backend.authorizeModel=async()=>{f.calls.push('authorize');f.context.parent={};return {ok:true,status:'authorized'};};
  f.backend.revokeModel=async value=>{revoked=value;f.calls.push('revoke');return {ok:true,status:'revoked'};};
  assert.equal((await f.invoke()).ok,false);assert.equal(revoked.session_token,TOKEN);
  assert.deepEqual(f.calls,['confirm','authorize','revoke']);
});

test('confirmed pro model uses trusted exact reservation and never consumes renderer cost',async t=>{
  const f=await fixture(t);await f.runtime.configure('deepseek-v4-pro');
  assert.equal((await f.invoke()).ok,true);
  assert.equal(f.details.model,'deepseek-v4-pro');assert.equal(f.details.max_total_usd,'0.10272768');
  assert.equal(f.payload.max_total_usd,'0.10272768');assert.equal(f.payload.valid_for_seconds,120);
  assert.equal(f.payload.expected_config_version,ID);
  assert.equal(f.requests.every(x=>x.method==='GET'),true);
});
