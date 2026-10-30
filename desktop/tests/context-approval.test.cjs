const {test}=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const {createHash}=require('node:crypto');
const {createModelSession}=require('../model-session.cjs');
const {registerModelApproval}=require('../model-approval.cjs');

const ID='11111111-2222-4333-8444-555555555555';
const REQUEST='aaaaaaaa-2222-4333-8444-555555555555';
const WORKSPACE='bbbbbbbb-2222-4333-8444-555555555555';
const CITATION='cccccccc-2222-4333-8444-555555555555';
const CITATION2='dddddddd-2222-4333-8444-555555555555';
const TOKEN='SYNTHETIC_CONTEXT_SESSION_20261021';
const CSRF='SYNTHETIC_CONTEXT_CSRF_20261021';
const CONTENT='仅用于本机测试的虚构问题。\n请按所选片段核对。';
const digest=value=>createHash('sha256').update(value,'utf8').digest('hex');

function previewFor(input,content,mutate={}) {
  const sources=input.citation_ids.map(id=>({saved_citation_id:id,
    title:id===CITATION?'合成法规片段':'合成案例片段',kind:id===CITATION?'law_markdown':'case_csv',
    line_start:3,line_end:9}));
  const basis={input_format:'library-context-v1',template_version:'saved-library-context-system-v1',
    request_id:input.request_id,expected_scope:{...input.expected_scope},
    expected_composer_revision:input.expected_composer_revision,system_sha256:digest('sys'),
    manifest_sha256:'b'.repeat(64),config_sha256:'c'.repeat(64),wire_sha256:'d'.repeat(64),
    source_bindings:input.citation_ids.map(id=>({saved_citation_id:id,citation_sha256:'e'.repeat(64)}))};
  return {scope:{...input.expected_scope},composer_revision:input.expected_composer_revision,
    manifest:{format_version:'saved-library-context-v1',question:content,sources},
    manifest_sha256:'b'.repeat(64),system_text:'合成系统提示',state:'ready',model:'deepseek-flash',
    config_sha256:'c'.repeat(64),max_input_bytes:65536,wire_payload_json:'{}',wire_sha256:'d'.repeat(64),
    wire_bytes:128,sending_enabled:false,send_basis:basis,...mutate};
}

async function fixture(t,options={}) {
  const scope={workspace_id:WORKSPACE,conversation_id:ID,scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:0};
  const input={conversation_id:ID,request_id:REQUEST,expected_scope:{...scope},
    expected_composer_revision:1,citation_ids:[CITATION,CITATION2]};
  const draft={scope:{...scope},draft_input:CONTENT,composer_revision:1,archived_at:null,latest_run:null};
  const materials={scope:{...scope},items:[],attachments:[]};
  const requests=[],calls=[];let payload,details;
  const backend={control:{ready:true,enabled:true,failed:false,closed:false},closing:false,
    async configureModel(){return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:ID};},
    async disableModel(){return {ok:true,status:'disabled'};},
    async authorizeModel(){calls.push('authorize');return {ok:true,status:'authorized'};},
    async authorizeContextModel(value){calls.push('authorize-context');payload=value;return {ok:true,status:'authorized'};},
    async revokeModel(){calls.push('revoke');return {ok:true,status:'revoked'};},
    async stop(){calls.push('stop');this.closing=true;}};
  const cookies=[{name:'qx_session',value:TOKEN},{name:'other',value:'ignored'}];
  if(!options.noCsrf)cookies.push({name:'qx_csrf',value:CSRF});
  const session={cookies:{async get(){return cookies;}}};
  const runtime=createModelSession({store:{async withSecret(fn){await fn('synthetic_key');return {status:'saved'};}},
    getBackend:()=>backend});
  await runtime.configure('deepseek-flash');
  const state={current:true,confirmResult:true};
  const server=http.createServer((req,res)=>{
    requests.push({path:req.url,method:req.method,cookie:req.headers.cookie,csrf:req.headers['x-csrf-token']});
    res.setHeader('Content-Type','application/json');
    if(req.url.endsWith('/materials'))return res.end(JSON.stringify(materials));
    if(req.url.endsWith('/context-preview') && req.method==='POST'){
      let raw='';req.on('data',chunk=>raw+=chunk);
      return req.on('end',()=>{
        if(req.headers['x-csrf-token']!==CSRF){res.statusCode=403;return res.end(JSON.stringify({code:'BLOCKED_LIVE'}));}
        const body=JSON.parse(raw);
        const mutation=typeof options.mutatePreview==='function'?options.mutatePreview(body):{};
        res.end(JSON.stringify(previewFor(body,CONTENT,mutation)));
      });
    }
    res.end(JSON.stringify(draft));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve);}));
  const origin='http://127.0.0.1:'+server.address().port;
  const event={},parent={},handlers=new Map();let busy=false;
  const context={origin,session,parent,backend,conversation_id:ID,guard:()=>state.current};
  registerModelApproval({ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},runtime,
    captureContext:value=>value===event?{...context}:null,isBusy:()=>busy,setBusy:value=>{busy=value;},
    async confirm(value){details=value.details;calls.push('confirm');return state.confirmResult;}});
  return {input,requests,calls,state,
    get payload(){return payload;},get details(){return details;},
    invoke:(value=input,sender=event)=>handlers.get('desktop:approve-context')(sender,value)};
}

test('approval shows the exact rebuilt selection and authorizes the server-built basis once',async t=>{
  const f=await fixture(t);
  assert.deepEqual(await f.invoke(),{ok:true});
  assert.deepEqual(f.calls,['authorize-context']);
  assert.equal(f.payload.session_token,TOKEN);
  assert.equal(f.payload.max_rounds,1);
  assert.equal(f.payload.basis.request_id,REQUEST);
  assert.deepEqual(f.payload.basis.source_bindings.map(binding=>binding.saved_citation_id),[CITATION,CITATION2]);
  const posts=f.requests.filter(request=>request.method==='POST');
  assert.ok(posts.length>=2,'the desktop re-reads the preview after the window decision');
  for(const post of posts)assert.equal(post.csrf,CSRF);
});

test('context send bypasses the old modal with both native previews intact',async t=>{
  const f=await fixture(t);f.state.confirmResult=false;
  assert.deepEqual(await f.invoke(),{ok:true});assert.deepEqual(f.calls,['authorize-context']);
  assert.equal(f.requests.filter(item=>item.method==='POST').length,2);
});

test('a preview that is not ready or carries a tampered basis is denied before any window',async t=>{
  for(const mutatePreview of [
    ()=>({state:'input_too_large',send_basis:null}),
    ()=>({send_basis:{...previewFor({citation_ids:[CITATION,CITATION2],request_id:REQUEST,
        expected_scope:{workspace_id:WORKSPACE,conversation_id:ID,scope_kind:'conversation',scope_ref:null,
          binding_revision:1,input_revision:0,materials_revision:0},expected_composer_revision:1},CONTENT)
        .send_basis,wire_sha256:'0'.repeat(64)}}),
    body=>({manifest:{...previewFor(body,CONTENT).manifest,
      sources:[...previewFor(body,CONTENT).manifest.sources].reverse()}}),
  ]){
    const f=await fixture(t,{mutatePreview});
    assert.deepEqual(await f.invoke(),{ok:false,code:'BLOCKED_LIVE'});
    assert.deepEqual(f.calls,[],'denied before confirmation and authorization');
  }
});

test('missing csrf cookie, busy desktop and malformed input are denied without a window',async t=>{
  const noCsrf=await fixture(t,{noCsrf:true});
  assert.deepEqual(await noCsrf.invoke(),{ok:false,code:'BLOCKED_LIVE'});
  assert.deepEqual(noCsrf.calls,[]);
  const f=await fixture(t);
  const first=f.invoke({...f.input,request_id:'99999999-2222-4333-8444-555555555555'});
  const second=f.invoke({...f.input,request_id:'88888888-2222-4333-8444-555555555555'});
  assert.deepEqual(await first,{ok:true});
  assert.deepEqual(await second,{ok:false,code:'STATE_CONFLICT'});
  assert.deepEqual(await f.invoke({...f.input,citation_ids:[CITATION,CITATION]}),{ok:false,code:'BLOCKED_LIVE'});
  assert.deepEqual(await f.invoke({...f.input,citation_ids:[]}),{ok:false,code:'BLOCKED_LIVE'});
  assert.deepEqual(await f.invoke({...f.input,extra:'x'}),{ok:false,code:'BLOCKED_LIVE'});
});
