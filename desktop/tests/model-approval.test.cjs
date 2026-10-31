const {test}=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const {createHash}=require('node:crypto');
const {createModelSession}=require('../model-session.cjs');
const ID='11111111-2222-4333-8444-555555555555';
const REQUEST='aaaaaaaa-2222-4333-8444-555555555555';
const WORKSPACE='bbbbbbbb-2222-4333-8444-555555555555';
const TOKEN='SYNTHETIC_APPROVAL_SESSION_20261019';
const CONTENT='仅用于本机测试的虚构文字。\n第二行保留完整空白。';
const digest=value=>createHash('sha256').update(value,'utf8').digest('hex');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
async function fixture(t,options={}) {
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
  let judgeRuntime,judgePayload;
  if(options.judge){
    Object.assign(backend.control,{judgeEnabled:true,judgeAuthorizationEnabled:true});
    Object.assign(backend,{
      async configureJudge(){return {ok:true,status:'configured',config_sha256:'b'.repeat(64),config_version:WORKSPACE};},
      async disableJudge(){return {ok:true,status:'disabled'};},
      async authorizeJudge(value){calls.push('judge-authorize');judgePayload=value;return {ok:true,status:'authorized'};},
      async revokeJudge(){calls.push('judge-revoke');return {ok:true,status:'revoked'};}
    });
    judgeRuntime=createModelSession({kind:'judge',judgeBudget:options.budget??null,getBackend:()=>backend,
      store:{async withSecret(fn){await fn('synthetic_judge_key');return {status:'saved'};}}});
    await judgeRuntime.configure('jev-1.13.0');
  }
  const state={current:true,confirmResult:true,betweenSnapshots:null,respond:null};
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
  const {registerModelApproval}=require('../model-approval.cjs');
  const optional=options.afterJudge?{withAuthorization:async(...args)=>{
    const result=await judgeRuntime.withAuthorization(...args);options.afterJudge({state,context,calls});return result;
  }}:judgeRuntime;
  const registration=registerModelApproval({ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},runtime,judgeRuntime:optional,
    captureContext:value=>value===event?{...context}:null,isBusy:()=>busy,setBusy:value=>{busy=value;},
    async confirm(){throw new Error('ordinary sends must not open a confirmation window');}});
  return {scope,input,draft,capability,materials,requests,calls,cookies,backend,runtime,judgeRuntime,session,state,context,
    get judgePayload(){return judgePayload;},
    registration,get payload(){return payload;},get details(){return details;},get busy(){return busy;},
    invoke:async (value=input,sender=event)=>{
      const previous=session.cookies.get,baseline=requests.length;let crossed=false;
      session.cookies.get=async(...args)=>{
        if(!crossed&&requests.length>=baseline+3){crossed=true;calls.push('boundary');if(state.betweenSnapshots)await state.betweenSnapshots();}
        return previous(...args);
      };
      try{return await handlers.get('desktop:approve-generation')(sender,value);}
      finally{session.cookies.get=previous;}
    }};
}
test('only trusted saved content and fixed model cost reach confirmation and one authorization',async t=>{
  const f=await fixture(t);
  assert.deepEqual(await f.invoke(),{ok:true});
  assert.deepEqual(f.calls,['boundary','authorize']);
  assert.equal(f.payload.session_token===TOKEN,true);
  assert.deepEqual(f.payload.basis,{request_id:REQUEST,expected_scope:f.scope,
    expected_composer_revision:1,content_sha256:digest(CONTENT)});
  assert.equal(f.requests.length,6);
  assert.equal(f.requests.every(item=>item.cookie==='qx_session='+TOKEN && item.method==='GET'),true);
});

test('obsolete confirmation callback cannot cancel the user-requested main send',async t=>{
  const f=await fixture(t);f.state.confirmResult=false;
  assert.deepEqual(await f.invoke(),{ok:true});assert.deepEqual(f.calls,['boundary','authorize']);
});

test('renderer-selected budget, malformed scope and other displayed conversations are refused before reads',async t=>{
  const f=await fixture(t);
  assert.equal((await f.invoke({...f.input,max_total_usd:'999'})).ok,false);
  assert.equal((await f.invoke({...f.input,expected_scope:{...f.scope,extra:true}})).ok,false);
  assert.equal((await f.invoke({...f.input,conversation_id:WORKSPACE,
    expected_scope:{...f.scope,conversation_id:WORKSPACE}})).code,'ACCESS_DENIED');
  assert.equal((await f.invoke(f.input,{})).code,'ACCESS_DENIED');
  assert.deepEqual(f.calls,[]);assert.deepEqual(f.requests,[]);assert.deepEqual(f.cookies,[]);
});

test('only an exact numeric owned loopback origin can receive a session cookie',async t=>{
  const f=await fixture(t);
  for(const origin of ['http://localhost:3000','http://127.0.0.1:1/extra','https://127.0.0.1:1',
    'http://127.0.0.1:1@invalid.test','http://127.0.0.1:65536','http://127.0.0.1:01']){
    f.context.origin=origin;assert.equal((await f.invoke()).ok,false);
  }
  assert.deepEqual(f.cookies,[]);assert.deepEqual(f.calls,[]);
});

test('all scope fields and composer revisions are checked independently of the content digest',async t=>{
  const f=await fixture(t);
  for(const [key,value] of [['workspace_id',REQUEST],['conversation_id',REQUEST],['scope_kind','intake'],
    ['scope_ref',REQUEST],['binding_revision',2],['input_revision',1],['materials_revision',1]]){
    const previous=f.draft.scope[key];f.draft.scope[key]=value;
    assert.equal((await f.invoke()).ok,false,key);f.draft.scope[key]=previous;
  }
  f.draft.composer_revision=2;assert.equal((await f.invoke()).ok,false);
  assert.deepEqual(f.calls,[]);
});

test('unapproved capability cannot hide selected attachments or a busy run',async t=>{
  const f=await fixture(t);
  f.materials.items.push({attachment_id:REQUEST});assert.equal((await f.invoke()).ok,false);
  f.materials.items=[];f.draft.latest_run={state:'queued'};assert.equal((await f.invoke()).ok,false);
  f.draft.latest_run=null;f.capability.state='restored_read_only';assert.equal((await f.invoke()).ok,false);
  assert.deepEqual(f.calls,[]);
});

test('materials and capability scope mismatches cannot reach confirmation',async t=>{
  const f=await fixture(t);f.materials.scope.materials_revision=1;
  assert.equal((await f.invoke()).ok,false);f.materials.scope.materials_revision=0;
  f.capability.scope.binding_revision=2;assert.equal((await f.invoke()).ok,false);
  assert.deepEqual(f.calls,[]);
});

test('changed saved content, composer or materials between snapshots never authorizes',async t=>{
  const f=await fixture(t);
  for(const change of [()=>{f.draft.draft_input+='变更';},()=>{f.draft.composer_revision++;},
    ()=>{f.materials.items.push({attachment_id:REQUEST});}]){
    f.state.betweenSnapshots=async()=>{change();return true;};
    assert.equal((await f.invoke()).ok,false);
    f.draft.draft_input=CONTENT;f.draft.composer_revision=1;f.materials.items=[];
  }
  assert.equal(f.calls.includes('authorize'),false);
});

test('ambiguous or target-specific cookies are rejected without authorization',async t=>{
  const f=await fixture(t);
  f.session.cookies.get=async()=>[{name:'qx_session',value:TOKEN},{name:'qx_session',value:TOKEN}];
  assert.equal((await f.invoke()).ok,false);
  f.session.cookies.get=async({url})=>[{name:'qx_session',value:url.endsWith('/materials')?'different_token':TOKEN}];
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,[]);assert.deepEqual(f.requests,[]);
});

test('a replaced session cookie between snapshots fails before authorization',async t=>{
  const f=await fixture(t);let token=TOKEN;
  f.session.cookies.get=async()=>[{name:'qx_session',value:token}];
  f.state.betweenSnapshots=async()=>{token='replacement_token';return true;};
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,['boundary']);
});

test('a cookie change after authorized ACK revokes the captured session',async t=>{
  const f=await fixture(t);let token=TOKEN,revoked;
  f.session.cookies.get=async()=>[{name:'qx_session',value:token}];
  f.backend.authorizeModel=async()=>{f.calls.push('authorize');token='replacement_token';return {ok:true,status:'authorized'};};
  f.backend.revokeModel=async value=>{f.calls.push('revoke');revoked=value;return {ok:true,status:'revoked'};};
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,['boundary','authorize','revoke']);
  assert.equal(revoked.session_token===TOKEN,true);
});

test('shared busy refuses duplicate clicks and wait includes the pending confirmation',async t=>{
  const f=await fixture(t),gate=deferred();f.state.betweenSnapshots=()=>gate.promise;
  const pending=f.invoke();while(!f.calls.includes('boundary'))await tick();
  assert.equal((await f.invoke()).code,'STATE_CONFLICT');
  assert.equal((await f.runtime.configure('deepseek-v4-pro')).code,'STATE_CONFLICT');
  let waited=false;const wait=f.registration.wait().then(()=>{waited=true;});await tick();
  assert.equal(waited,false);assert.equal(f.busy,true);
  gate.resolve();assert.equal((await pending).ok,true);await wait;assert.equal(f.busy,false);
});

test('document change between snapshots cannot authorize even if the window returns true',async t=>{
  const f=await fixture(t);f.state.betweenSnapshots=async()=>{f.state.current=false;return true;};
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,['boundary']);
});

test('redirects, oversized bodies and malformed UTF8 are rejected as fixed errors',async t=>{
  const f=await fixture(t);
  for(const respond of [
    (req,res)=>{res.writeHead(302,{Location:'http://invalid.test/'});res.end();return true;},
    (req,res)=>{res.setHeader('Content-Type','application/json');res.end(' '.repeat(262145));return true;},
    (req,res)=>{res.setHeader('Content-Type','application/json');res.end(Buffer.from([0xff]));return true;}
  ]){
    f.state.respond=respond;assert.deepEqual(await f.invoke(),{ok:false,code:'BLOCKED_LIVE'});
  }
  assert.deepEqual(f.calls,[]);
});

test('repeated confirmation keeps the same request and budget and accepts an existing receipt',async t=>{
  const f=await fixture(t),authorizations=[];
  f.backend.authorizeModel=async value=>{authorizations.push(value);return {ok:true,status:authorizations.length===1?'authorized':'existing'};};
  assert.deepEqual(await f.invoke(),{ok:true});assert.deepEqual(await f.invoke(),{ok:true});
  assert.equal(authorizations.length,2);assert.deepEqual(authorizations[1],authorizations[0]);
  assert.equal(authorizations[1].max_total_usd,null);assert.equal(authorizations[1].valid_for_seconds,120);
});

test('exhausted previous approval permits a new explicit one-call confirmation',async t=>{
  const f=await fixture(t);f.capability.state='budget_exhausted';
  assert.deepEqual(await f.invoke(),{ok:true});
  assert.deepEqual(f.calls,['boundary','authorize']);
  assert.equal(f.payload.max_total_usd,null);assert.equal(f.payload.valid_for_seconds,120);
});

test('a stalled owned HTTP response times out with fixed output and releases the busy lock',async t=>{
  const f=await fixture(t);f.state.respond=()=>true;
  const started=Date.now();
  assert.deepEqual(await f.invoke(),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(Date.now()-started<8000,true);assert.equal(f.busy,false);assert.deepEqual(f.calls,[]);
});

test('HTTP permission denial and malformed JSON never forward server error text to the renderer',async t=>{
  const f=await fixture(t);
  for(const status of [403,200]){
    f.state.respond=(req,res)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end('synthetic malformed response');return true;};
    assert.deepEqual(await f.invoke(),{ok:false,code:'BLOCKED_LIVE'});
  }
  assert.deepEqual(f.calls,[]);
});

test('missing cookie and a cookie with header delimiters are refused before any request',async t=>{
  const f=await fixture(t);
  for(const values of [[],[{name:'qx_session',value:'unsafe; other=value'}]]){
    f.session.cookies.get=async()=>values;assert.equal((await f.invoke()).ok,false);
  }
  assert.deepEqual(f.requests,[]);assert.deepEqual(f.calls,[]);
});

test('a changed context identity cannot reuse the same guard function to approve',async t=>{
  const f=await fixture(t);const original=f.context.parent;
  // A fresh context with a new parent is what captureContext must report on replacement.
  f.state.betweenSnapshots=async()=>{f.context.parent={};return true;};
  assert.equal((await f.invoke()).ok,false);
  assert.notEqual(f.context.parent,original);assert.deepEqual(f.calls,['boundary']);
});

for(const budget of [null,'0.02'])test('configured Judge is not implicitly opted in by a main send '+budget,async t=>{
  const f=await fixture(t,{judge:true,budget});
  assert.deepEqual(await f.invoke(),{ok:true});assert.deepEqual(f.calls,['boundary','authorize']);
  assert.equal(f.judgePayload,undefined);
});
test('main refusal never grants an optional Judge',async t=>{
  const f=await fixture(t,{judge:true,budget:'0.02'});
  f.backend.authorizeModel=async()=>{f.calls.push('authorize');return {ok:false,code:'VERSION_CONFLICT'};};
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,['boundary','authorize']);
});

test('unconfigured revoked and archived main sends cannot acquire a lease',async t=>{
  const f=await fixture(t);f.draft.archived_at='2026-10-30T00:00:00Z';
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,[]);
  f.draft.archived_at=null;f.state.current=false;
  assert.equal((await f.invoke()).ok,false);assert.deepEqual(f.calls,[]);
  f.state.current=true;await f.runtime.disable();const before=f.requests.length;
  assert.equal((await f.invoke()).ok,false);assert.equal(f.requests.length,before);assert.deepEqual(f.calls,[]);
});
