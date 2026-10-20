// Real Windows safeStorage + owned pipes + actual HTTP app; synthetic only.
// Not in build.files; no renderer or external provider is used.
const {app,safeStorage}=require('electron');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const assert=require('node:assert/strict');
const {randomUUID,createHash}=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {Backend}=require('../backend.cjs');
const {createModelCredentialStore}=require('../model-credentials.cjs');
const project=path.resolve(__dirname,'../..');
const target=path.resolve(process.argv[2]);
const options=process.argv.slice(3);
const judgeMode=options.includes('--judge'),frozenIndex=options.indexOf('--frozen');
const frozen=frozenIndex<0?null:path.resolve(options[frozenIndex+1]||'');
assert(options.every((value,index)=>value==='--judge'||value==='--frozen'||(frozenIndex>=0&&index===frozenIndex+1)));
assert(!frozen||(judgeMode&&options[frozenIndex+1]&&fs.statSync(frozen).isFile()));
fs.mkdirSync(target,{recursive:false});
app.setPath('userData',path.join(target,'electron-profile'));
const report={scope:'native private control, not daily approval UI',electron:process.versions.electron,
  mode:frozen?'frozen-control-only':judgeMode?'source-main-and-judge':'source-main',
  external_provider_execution:'not_requested',
  renderer_ipc:'not_exercised_by_this_headless_private_pipe_driver',checks:[]};
const secret='SYNTHETIC_NATIVE_PIPE_NOT_A_REAL_KEY_12345';
const judgeSecret='SYNTHETIC_JUDGE_PIPE_NOT_A_REAL_KEY_67890';
const content='独立合成咨询：请整理虚构客户提出的交货问题。';
const hash=s=>createHash('sha256').update(s).digest('hex');
let backend,upstream,judgeUpstream,cookie='',csrf='',token='',posts=0,judgePosts=0,wire=[],order=[];
const check=name=>report.checks.push(name);
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
  await app.whenReady();
  if(!frozen)upstream=http.createServer(async(req,res)=>{
    try{
      const chunks=[];for await(const part of req)chunks.push(part);
      assert.equal(req.method,'POST');assert.equal(req.url,'/chat/completions');assert.equal(req.headers.authorization,'Bearer '+secret);
      const value=JSON.parse(Buffer.concat(chunks));
      const source=JSON.parse(value.messages[1].content);assert.equal(source.content,content);posts++;order.push('main');
      const candidate={text:'独立合成候选：交货事项仍需律师核对。',citations:[
        {message_id:source.message_id,quote_sha256:source.quote_sha256}]};
      const body=JSON.stringify({id:'synthetic-native-response',model:'deepseek-flash',
        object:'chat.completion',created:1,
        choices:[{index:0,finish_reason:'stop',message:{role:'assistant',content:JSON.stringify(candidate)}}],
        usage:{prompt_tokens:30,completion_tokens:12,total_tokens:42}});
      res.writeHead(200,{'Content-Type':'application/json'});res.end(body);
    }catch{res.writeHead(500);res.end('{}');report.provider_error=true;}
  });
  if(upstream)await new Promise(r=>upstream.listen(0,'127.0.0.1',r));
  const endpoint=upstream?`http://127.0.0.1:${upstream.address().port}/chat/completions`:null;
  if(judgeMode&&!frozen){
    judgeUpstream=http.createServer(async(req,res)=>{
      try{
        const chunks=[];for await(const part of req)chunks.push(part);
        assert.equal(req.method,'POST');assert.equal(req.url,'/v1/systemone');
        assert.equal(req.headers.authorization,'Bearer '+judgeSecret);
        const value=JSON.parse(Buffer.concat(chunks));
        assert.equal(value.model,'jev-1.13.0');assert.deepEqual(value.state,{latest_request:content,selected_skill:null});
        assert.deepEqual(Object.keys(value.questions),['primary_intent']);
        judgePosts++;order.push('judge');
        const probabilities={client_reply:1,material_organize:0,contract_review:0,content_draft:0,legal_research:0,unknown:0};
        res.writeHead(200,{'Content-Type':'application/json','x-typesafe-request-id':'synthetic-native-judge'});
        res.end(JSON.stringify({model:'jev-1.13.0',answers:{primary_intent:{type:'choice',choice:'client_reply',
          probabilities,confidence:1}},usage:{input_tokens:25,output_tokens:2}}));
      }catch{res.writeHead(500);res.end('{}');report.judge_provider_error=true;}
    });
    await new Promise(r=>judgeUpstream.listen(0,'127.0.0.1',r));
  }
  const judgeEndpoint=judgeUpstream?`http://127.0.0.1:${judgeUpstream.address().port}/v1/systemone`:null;
  const parent=path.join(target,'合成 中文 资料');
  const store=createModelCredentialStore({dataParent:parent,safeStorage});
  const judgeStore=judgeMode?createModelCredentialStore({dataParent:parent,safeStorage,provider:'typesafe'}):null;
  assert.deepEqual(await store.save(secret),{status:'saved'});
  const ciphertext=fs.readFileSync(path.join(parent,'model-credentials/deepseek.bin'));
  assert(!ciphertext.includes(Buffer.from(secret)));check('real_safeStorage_ciphertext');
  if(judgeStore){
    assert.deepEqual(await judgeStore.save(judgeSecret),{status:'saved'});
    const judgeCiphertext=fs.readFileSync(path.join(parent,'model-credentials/typesafe.bin'));
    assert(!judgeCiphertext.includes(Buffer.from(judgeSecret)));assert(!judgeCiphertext.equals(ciphertext));
    check('independent_typesafe_safeStorage_ciphertext');
  }
  let starts=0;
  const create=()=>{
    starts++;
    const args=['-X','utf8',path.join(project,'tests/helpers/synthetic_native_control_entry.py'),endpoint];
    if(judgeMode&&!frozen)args.push('--judge',judgeEndpoint,path.join(target,`network-${starts}.json`));
    const instance=new Backend(frozen||path.join(project,'.venv/Scripts/python.exe'),frozen?[]:args);
    return instance;
  };
  const inspect=(run)=>JSON.parse(execFileSync(path.join(project,'.venv/Scripts/python.exe'),[
    '-X','utf8',path.join(project,'tests/helpers/inspect_native_control_records.py'),
    path.join(parent,'workspaces/main/workbench.db'),...(run?['--run',run,'--hash',hash(content)]:[])],
    {encoding:'utf8',windowsHide:true,env:{...process.env,PYTHONPATH:path.join(project,'src')}}));
  backend=create();
  let ready=await backend.start({data_parent:parent,username:'合成管道律师',password:'fixture123'});
  if(judgeMode)assert.equal(ready.judge_authorization_protocol,'qx-judge-authorization-v1');
  let base=`http://127.0.0.1:${ready.port}`;
  backend.child.stdout.on('data',b=>wire.push(b));backend.child.stderr.on('data',b=>wire.push(b));
  async function call(url,method='GET',body){
    const response=await fetch(base+url,{method,headers:{Cookie:cookie,Origin:base,
      'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json();
    return {response,data};
  }
  async function login(){
    const {response,data}=await call('/api/login','POST',{username:'合成管道律师',password:'fixture123'});
    assert.equal(response.status,200);
    cookie=response.headers.getSetCookie().map(s=>s.split(';')[0]).join('; ');
    token=cookie.match(/qx_session=([^;]+)/)[1];csrf=data.csrf_token;
  }
  await login();
  let {response,data:view}=await call('/api/assistant/conversations','POST',{request_id:randomUUID()});
  assert.equal(response.status,201);
  const url='/api/assistant/conversations/'+view.scope.conversation_id;
  ({response,data:view}=await call(url+'/draft','PUT',{expected_scope:view.scope,
    expected_composer_revision:view.composer_revision,content}));assert.equal(response.status,200);
  assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
  const config={enabled:true,model:'deepseek-flash',input_usd_per_million:'0.3',
    output_usd_per_million:'1.2',price_reference:'synthetic-only',timeout_seconds:15};
  let configured;
  assert.deepEqual(await store.withSecret(async value=>{
    configured=await backend.configureModel({config,secret:value});return value;
  }),{status:'saved'});
  assert.equal(configured.ok,true);assert.equal(configured.status,'configured');
  let judgeConfigured;
  if(judgeStore){
    assert.deepEqual(await judgeStore.withSecret(async value=>{
      judgeConfigured=await backend.configureJudge({config:{enabled:true},secret:value});return value;
    }),{status:'saved'});
    assert.equal(judgeConfigured.ok,true);assert.equal(judgeConfigured.status,'configured');
  }
  assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
  const request={request_id:randomUUID(),expected_scope:view.scope,
    expected_composer_revision:view.composer_revision,content};
  const approval={session_token:token,expected_config_version:configured.config_version,
    basis:{request_id:request.request_id,expected_scope:request.expected_scope,
      expected_composer_revision:request.expected_composer_revision,content_sha256:hash(content)},
    max_total_usd:'1',valid_for_seconds:120};
  const judgeApproval=judgeMode?{...approval,expected_config_version:judgeConfigured.config_version,
    basis:{...approval.basis,purpose:'primary_intent'},max_total_usd:'0.02'}:null;
  assert.equal((await backend.authorizeModel({...approval,session_token:'invalid-synthetic-session'})).ok,false);
  assert.deepEqual(await backend.authorizeModel(approval),{ok:true,status:'authorized'});
  assert.deepEqual(await backend.authorizeModel(approval),{ok:true,status:'authorized'});
  assert.equal((await call(url+'/generation-capability')).data.state,'ready');
  if(!frozen){
    const denied=await call(url+'/generations','POST',{...request,request_id:randomUUID()});
    assert.equal(denied.response.status,403);assert.equal(posts,0);
  }
  check('configured_without_grant_then_exact_single_intent');
  if(judgeMode){
    assert.equal((await backend.authorizeJudge({...judgeApproval,session_token:'invalid-synthetic-session'})).ok,false);
    assert.deepEqual(await backend.authorizeJudge(judgeApproval),{ok:true,status:'authorized'});
    assert.deepEqual(await backend.authorizeJudge(judgeApproval),{ok:true,status:'authorized'});
    assert.equal(judgePosts,0);
    // Ordinary HTTP has no native authorize/configure endpoint. No approval payload is posted.
    for(const name of ['authorize_judge','configure_judge','judge/authorize','judge/configure']){
      const deniedHTTP=await fetch(base+'/api/assistant/'+name,{method:'POST',headers:{Cookie:cookie,Origin:base,
        'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'});
      assert([404,405].includes(deniedHTTP.status));
    }
    check('independent_judge_grant_and_no_native_http_endpoint');
  }
  if(frozen){
    assert.deepEqual(await backend.revokeJudge({session_token:token}),{ok:true,status:'revoked'});
    assert.deepEqual(await backend.revokeModel({session_token:token}),{ok:true,status:'revoked'});
    assert.equal((await backend.authorizeJudge(judgeApproval)).ok,false);
    assert.equal((await backend.authorizeModel(approval)).ok,false);
    assert.deepEqual(await backend.disableJudge(),{ok:true,status:'disabled'});
    assert.deepEqual(await backend.disableModel(),{ok:true,status:'disabled'});
    assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
    assert.equal((await call(url+'/generations','POST',request)).response.status,403);
    report.ledger=inspect();check('frozen_two_native_grants_revoked_disabled_submission_denied');
    await backend.stop();await backend.exited;assert.equal(backend.child.exitCode,0);
    backend=create();ready=await backend.start({data_parent:parent});base=`http://127.0.0.1:${ready.port}`;
    backend.child.stdout.on('data',b=>wire.push(b));backend.child.stderr.on('data',b=>wire.push(b));
    assert.equal(ready.judge_authorization_protocol,'qx-judge-authorization-v1');
    assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
    assert.equal((await backend.authorizeJudge(judgeApproval)).ok,false);
    assert.equal((await backend.authorizeModel(approval)).ok,false);
    assert.equal((await call(url+'/generations','POST',request)).response.status,403);
    report.restart_ledger=inspect();check('frozen_eof_restart_has_no_authority_or_persisted_attempt');
    await backend.stop();assert.equal(backend.child.exitCode,0);
  }else{
  const submitted=await call(url+'/generations','POST',request);assert.equal(submitted.response.status,202);
  const id=submitted.data.id;
  let result;
  for(let i=0;i<300;i++){
    result=(await call('/api/assistant/attempts/'+id)).data;
    if(result.receipt)break;await delay(50);
  }
  assert.equal(result.state,'received');assert.equal(result.output.review_status,'unverified');
  assert.equal(result.output.audience,'internal');
  assert.equal(result.output.candidate.citations[0].quote_sha256,hash(content));
  assert.equal(posts,1);assert.equal((await call(url+'/generations','POST',request)).data.id,id);
  assert.deepEqual(await backend.authorizeModel(approval),{ok:true,status:'existing'});assert.equal(posts,1);
  check('real_pipe_http_receipt_citation_and_replay_one_post');
  if(judgeMode){
    assert.equal(judgePosts,1);assert.deepEqual(order,['judge','main']);
    assert.deepEqual(await backend.authorizeJudge(judgeApproval),{ok:true,status:'existing'});
    report.ledger=inspect(result.run_id);
    assert.deepEqual(await backend.revokeJudge({session_token:token}),{ok:true,status:'revoked'});
    assert.deepEqual(await backend.disableJudge(),{ok:true,status:'disabled'});
    check('one_judge_then_main_same_run_full_source_hash_unknown_cost_unverified');
  }
  assert.deepEqual(await backend.revokeModel({session_token:token}),{ok:true,status:'revoked'});
  assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
  assert.deepEqual(await backend.disableModel(),{ok:true,status:'disabled'});
  await backend.stop();await backend.exited;
  assert.equal(backend.child.exitCode,0);check('revoke_disable_eof_clean_shutdown');
  backend=create();ready=await backend.start({data_parent:parent});base=`http://127.0.0.1:${ready.port}`;
  backend.child.stdout.on('data',b=>wire.push(b));backend.child.stderr.on('data',b=>wire.push(b));
  assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
  assert.equal((await call('/api/assistant/attempts/'+id)).data.output.candidate.citations[0].quote_sha256,hash(content));
  assert.equal((await call(url+'/generations','POST',request)).response.status,403);
  assert.equal((await call(url+'/generations/by-request/'+request.request_id)).data.id,id);assert.equal(posts,1);
  if(judgeMode){
    assert.equal((await backend.authorizeJudge(judgeApproval)).ok,false);
    assert.equal(judgePosts,1);assert.deepEqual(inspect(result.run_id),report.ledger);
    const network=JSON.parse(fs.readFileSync(path.join(target,'network-1.json')));
    const restarted=JSON.parse(fs.readFileSync(path.join(target,'network-2.json')));
    assert.deepEqual(network,{main:1,judge:1,blocked_other_httpx_requests:0});
    assert.deepEqual(restarted,{main:0,judge:0,blocked_other_httpx_requests:0});
    report.httpx_tripwire={scope:'source child httpx/httpx2 Client.send and AsyncClient.send only',first:network,restart:restarted};
    check('source_httpx_exact_endpoint_tripwire_and_restart_no_resend');
  }
  await backend.stop();assert.equal(backend.child.exitCode,0);check('restart_empty_registry_history_read_without_resend');
  }
  const db=fs.readFileSync(path.join(parent,'workspaces/main/workbench.db'));
  for(const bytes of [Buffer.concat(wire),db,Buffer.from(JSON.stringify(report))]){
    assert(!bytes.includes(Buffer.from(secret)));assert(!bytes.includes(Buffer.from(judgeSecret)));
    assert(!bytes.includes(Buffer.from(token)));
  }
  check('no_plaintext_secret_or_session_token_in_ack_logs_database');
  await store.remove();await store.drain();
  if(judgeStore){await judgeStore.remove();await judgeStore.drain();}
  report.status='passed';report.upstream_posts=posts;report.judge_upstream_posts=judgePosts;
  report.observed_post_order=order;
  report.network_limit=frozen?'No provider execution requested; no whole-process network counter installed.':
    'Only the two explicitly created loopback server counters (and optional source httpx tripwire) were observed; not a whole-process network audit.';
}
main().catch(error=>{report.status='failed';report.error_type=error.name;
  report.error_code=error.code||'ACCEPTANCE_FAILED';process.exitCode=1;
  if(/^BACKEND_[A-Z_]+$/.test(error.message))report.error_code=error.message;
  report.error_location=String(error.stack).match(/model-control-acceptance\.cjs:\d+:\d+/)?.[0];
}).finally(async()=>{
  if(backend)await backend.stop();
  if(upstream)await new Promise(r=>upstream.close(r));
  if(judgeUpstream)await new Promise(r=>judgeUpstream.close(r));
  fs.writeFileSync(path.join(target,'report.json'),JSON.stringify(report,null,2));
  app.exit(report.status==='passed'?0:1);
});
