// Real Windows safeStorage + owned pipes + actual HTTP app; synthetic only.
// Not in build.files; no renderer or external provider is used.
const {app,safeStorage}=require('electron');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const assert=require('node:assert/strict');
const {randomUUID,createHash}=require('node:crypto');
const {Backend}=require('../backend.cjs');
const {createModelCredentialStore}=require('../model-credentials.cjs');
const project=path.resolve(__dirname,'../..');
const target=path.resolve(process.argv[2]);
fs.mkdirSync(target,{recursive:false});
app.setPath('userData',path.join(target,'electron-profile'));
const report={scope:'native private control, not daily approval UI',electron:process.versions.electron,
  real_model_calls:0,checks:[]};
const secret='SYNTHETIC_NATIVE_PIPE_NOT_A_REAL_KEY_12345';
const content='独立合成咨询：请整理虚构客户提出的交货问题。';
const hash=s=>createHash('sha256').update(s).digest('hex');
let backend,upstream,cookie='',csrf='',token='',posts=0,wire=[];
const check=name=>report.checks.push(name);
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
  await app.whenReady();
  upstream=http.createServer(async(req,res)=>{
    try{
      const chunks=[];for await(const part of req)chunks.push(part);
      assert.equal(req.url,'/chat/completions');assert.equal(req.headers.authorization,'Bearer '+secret);
      const value=JSON.parse(Buffer.concat(chunks));
      const source=JSON.parse(value.messages[1].content);assert.equal(source.content,content);posts++;
      const candidate={text:'独立合成候选：交货事项仍需律师核对。',citations:[
        {message_id:source.message_id,quote_sha256:source.quote_sha256}]};
      const body=JSON.stringify({id:'synthetic-native-response',model:'deepseek-flash',
        object:'chat.completion',created:1,
        choices:[{index:0,finish_reason:'stop',message:{role:'assistant',content:JSON.stringify(candidate)}}],
        usage:{prompt_tokens:30,completion_tokens:12,total_tokens:42}});
      res.writeHead(200,{'Content-Type':'application/json'});res.end(body);
    }catch{res.writeHead(500);res.end('{}');report.provider_error=true;}
  });
  await new Promise(r=>upstream.listen(0,'127.0.0.1',r));
  const endpoint=`http://127.0.0.1:${upstream.address().port}/chat/completions`;
  const parent=path.join(target,'合成 中文 资料');
  const store=createModelCredentialStore({dataParent:parent,safeStorage});
  assert.deepEqual(await store.save(secret),{status:'saved'});
  const ciphertext=fs.readFileSync(path.join(parent,'model-credentials/deepseek.bin'));
  assert(!ciphertext.includes(Buffer.from(secret)));check('real_safeStorage_ciphertext');
  const create=()=>{
    const instance=new Backend(path.join(project,'.venv/Scripts/python.exe'),[
      '-X','utf8',path.join(project,'tests/helpers/synthetic_native_control_entry.py'),endpoint]);
    return instance;
  };
  backend=create();
  let ready=await backend.start({data_parent:parent,username:'合成管道律师',password:'fixture123'});
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
  assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
  const request={request_id:randomUUID(),expected_scope:view.scope,
    expected_composer_revision:view.composer_revision,content};
  const approval={session_token:token,expected_config_version:configured.config_version,
    basis:{request_id:request.request_id,expected_scope:request.expected_scope,
      expected_composer_revision:request.expected_composer_revision,content_sha256:hash(content)},
    max_total_usd:'1',valid_for_seconds:120};
  assert.equal((await backend.authorizeModel({...approval,session_token:'invalid-synthetic-session'})).ok,false);
  assert.deepEqual(await backend.authorizeModel(approval),{ok:true,status:'authorized'});
  assert.deepEqual(await backend.authorizeModel(approval),{ok:true,status:'authorized'});
  assert.equal((await call(url+'/generation-capability')).data.state,'ready');
  const denied=await call(url+'/generations','POST',{...request,request_id:randomUUID()});
  assert.equal(denied.response.status,403);assert.equal(posts,0);
  check('configured_without_grant_then_exact_single_intent');
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
  assert.deepEqual(await backend.revokeModel({session_token:token}),{ok:true,status:'revoked'});
  assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
  assert.deepEqual(await backend.disableModel(),{ok:true,status:'disabled'});
  await backend.stop();await backend.exited;
  assert.equal(backend.child.exitCode,0);check('revoke_disable_eof_clean_shutdown');
  backend=create();ready=await backend.start({data_parent:parent});base=`http://127.0.0.1:${ready.port}`;
  assert.notEqual((await call(url+'/generation-capability')).data.state,'ready');
  assert.equal((await call('/api/assistant/attempts/'+id)).data.output.candidate.citations[0].quote_sha256,hash(content));
  assert.equal((await call(url+'/generations','POST',request)).response.status,403);
  assert.equal((await call(url+'/generations/by-request/'+request.request_id)).data.id,id);assert.equal(posts,1);
  await backend.stop();assert.equal(backend.child.exitCode,0);check('restart_empty_registry_history_read_without_resend');
  const db=fs.readFileSync(path.join(parent,'workspaces/main/workbench.db'));
  for(const bytes of [Buffer.concat(wire),db,Buffer.from(JSON.stringify(report))]){
    assert(!bytes.includes(Buffer.from(secret)));assert(!bytes.includes(Buffer.from(token)));
  }
  check('no_plaintext_secret_or_session_token_in_ack_logs_database');
  await store.remove();await store.drain();report.status='passed';report.upstream_posts=posts;
}
main().catch(error=>{report.status='failed';report.error_type=error.name;
  report.error_code=error.code||'ACCEPTANCE_FAILED';process.exitCode=1;
  if(/^BACKEND_[A-Z_]+$/.test(error.message))report.error_code=error.message;
  report.error_location=String(error.stack).match(/model-control-acceptance\.cjs:\d+:\d+/)?.[0];
}).finally(async()=>{
  if(backend)await backend.stop();
  if(upstream)await new Promise(r=>upstream.close(r));
  fs.writeFileSync(path.join(target,'report.json'),JSON.stringify(report,null,2));
  app.exit(report.status==='passed'?0:1);
});
