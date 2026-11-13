const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createCaseMemoryRuntime,buildServiceEnvironment,lockFromPlan}=require('./case-memory-runtime.cjs');
function fixture(t){const data=fs.mkdtempSync(path.join(os.tmpdir(),'qx-memory-runtime-'));t.after(()=>fs.rmSync(data,{recursive:true,force:true}));return data;}
test('default-on feature exposes honest uninstalled status, protects control and keeps stable datastore identity',async t=>{
  const data=fixture(t);let runtime=await createCaseMemoryRuntime({data,payload:data,python:process.execPath,secret:'synthetic-secret'});
  t.after(async()=>runtime.stop());
  const firstId=runtime.env.QX_HINDSIGHT_INSTANCE_ID;
  assert.equal(runtime.status().phase,'not-installed');assert.match(runtime.env.QX_HINDSIGHT_URL,/^http:\/\/127\.0\.0\.1:\d+\/engine$/);
  const base=runtime.env.QX_CASE_MEMORY_CONTROL_URL,headers={Authorization:`Bearer ${runtime.env.QX_CASE_MEMORY_CONTROL_TOKEN}`};
  assert.equal((await fetch(base+'/status')).status,401);
  assert.equal((await fetch(base+'/status',{headers:{Authorization:'é'.repeat(headers.Authorization.length)}})).status,401);
  assert.equal((await fetch(base+'/status',{headers:{...headers,Origin:'http://unrelated.test'}})).status,403);
  const state=await (await fetch(base+'/status',{headers})).json();assert.equal(state.phase,'not-installed');assert.ok(!JSON.stringify(state).includes('synthetic-secret'));
  assert.equal((await fetch(runtime.env.QX_HINDSIGHT_URL+'/v1/default/banks',{headers:{Authorization:`Bearer ${runtime.env.QX_HINDSIGHT_TOKEN}`}})).status,503);
  await runtime.stop();runtime=await createCaseMemoryRuntime({data,payload:data,python:process.execPath});
  assert.equal(runtime.env.QX_HINDSIGHT_INSTANCE_ID,firstId);await runtime.stop();
});
test('service configuration binds locally, authenticates native API, isolates data and disables hidden paid consolidation',()=>{
  const env=buildServiceEnvironment({root:'D:/isolated-memory',instance:{id:'abc',databasePassword:'db-secret'},secret:'model-secret',token:'api-secret',port:9123,model:'deepseek-flash'});
  assert.equal(env.HINDSIGHT_API_HOST,'127.0.0.1');assert.equal(env.HINDSIGHT_API_TENANT_API_KEY,'api-secret');
  assert.match(env.HINDSIGHT_API_TENANT_EXTENSION,/ApiKeyTenantExtension$/);assert.equal(env.HINDSIGHT_API_EMBEDDINGS_PROVIDER,'onnx');
  assert.equal(env.HINDSIGHT_API_RERANKER_PROVIDER,'rrf');assert.equal(env.HINDSIGHT_API_ENABLE_AUTO_CONSOLIDATION,'false');
  assert.equal(env.HINDSIGHT_API_SKIP_LLM_VERIFICATION,'true','preparation must not invoke paid model verification');
  assert.equal(env.HINDSIGHT_API_LLM_MODEL,'deepseek-flash');assert.equal(env.HINDSIGHT_API_LLM_API_KEY,'model-secret');
  assert.ok(!('PG0_HOME' in env));assert.ok(!('HOME' in env));assert.ok(!('DEEPSEEK_API_KEY' in env));
  assert.equal(env.QX_MEMORY_DATABASE_DIR,path.join('D:/isolated-memory','database'));
});
test('dependency plan becomes an integrity-pinned lock and rejects Torch, source distributions or nonregistry downloads',()=>{
  const row={metadata:{name:'example',version:'1.0'},download_info:{url:'https://files.pythonhosted.org/example.whl',archive_info:{hashes:{sha256:'a'.repeat(64)}}}};
  assert.match(lockFromPlan({install:[row]}),/--hash=sha256:aaaa/);
  assert.throws(()=>lockFromPlan({install:[{...row,metadata:{name:'torch',version:'1'}}]}),/dependency/);
  assert.throws(()=>lockFromPlan({install:[{...row,download_info:{...row.download_info,url:'https://unknown.test/example.whl'}}]}),/dependency/);
});

test('a copied datastore identity uses a different pg0 registration while path spelling stays stable',()=>{
  const options={instance:{id:'11111111-1111-4111-8111-111111111111',databasePassword:'ab'.repeat(32)},secret:'synthetic',token:'synthetic',port:9012,model:'synthetic'};
  const first=buildServiceEnvironment({...options,root:path.resolve('synthetic-source')}),copy=buildServiceEnvironment({...options,root:path.resolve('synthetic-copy')});
  assert.notEqual(new URL(first.HINDSIGHT_API_DATABASE_URL).hostname,new URL(copy.HINDSIGHT_API_DATABASE_URL).hostname);
  const spelling=buildServiceEnvironment({...options,root:path.resolve('synthetic-source','..','synthetic-source')});
  assert.equal(new URL(first.HINDSIGHT_API_DATABASE_URL).hostname,new URL(spelling.HINDSIGHT_API_DATABASE_URL).hostname);
  if(process.platform==='win32')assert.equal(new URL(first.HINDSIGHT_API_DATABASE_URL).hostname,new URL(buildServiceEnvironment({...options,root:path.resolve('synthetic-source').toUpperCase()}).HINDSIGHT_API_DATABASE_URL).hostname);
  assert.equal('PG0_HOME' in first,false,'unsupported upstream setting must not imply isolated registration');
});

test('refusing a foreign or unreadable pg0 registration never starts or stops that database',{skip:!process.env.QX_TEST_PYTHON},async t=>{
  for(const fault of ['foreign','unreadable'])await t.test(fault,async t=>{
    const data=fixture(t),modules=path.join(data,'modules'),actions=path.join(data,'actions');fs.mkdirSync(modules);
    fs.writeFileSync(path.join(modules,'pg0.py'),`import os\nfrom pathlib import Path\nfrom types import SimpleNamespace\nclass Pg0:\n def __init__(self,**kwargs): pass\n def info(self):\n  if os.environ['TEST_FAULT']=='unreadable': raise ValueError('synthetic broken registration')\n  return SimpleNamespace(data_dir=os.environ['TEST_FOREIGN'],running=True)\n def start(self):\n  Path(os.environ['TEST_ACTIONS']).write_text('started')\n  raise RuntimeError('unexpected start')\n def stop(self): Path(os.environ['TEST_ACTIONS']).write_text('stopped')\n`);
    const directory=path.join(data,'.local/case-memory-runtime'),interpreter=path.join(directory,'venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
    fs.mkdirSync(path.dirname(interpreter),{recursive:true});fs.writeFileSync(interpreter,'synthetic');fs.writeFileSync(path.join(directory,'installed.json'),JSON.stringify({version:'1.2.0'}));
    const runtime=await createCaseMemoryRuntime({data,payload:data,secret:'synthetic',startupTimeoutMs:5000,
      spawnProcess(command,args,options){return spawn(process.env.QX_TEST_PYTHON,args,{...options,env:{...options.env,PYTHONPATH:modules,TEST_FAULT:fault,TEST_FOREIGN:path.join(data,'other-database'),TEST_ACTIONS:actions}});}});
    t.after(()=>runtime.stop());await runtime.prepare();assert.equal(runtime.status().phase,'error');await runtime.stop();
    assert.equal(fs.existsSync(actions),false,'a rejected registration must not be started or stopped by fallback cleanup');
  });
});
test('failed preparation exposes safe retryable status and no installed marker',async t=>{
  const data=fixture(t);
  const runtime=await createCaseMemoryRuntime({data,payload:data,python:process.execPath,secret:'synthetic-secret',spawnProcess:()=>spawn(process.execPath,['-e','process.exit(3)'],{stdio:['pipe','pipe','pipe']})});
  await runtime.prepare();assert.equal(runtime.status().phase,'error');
  assert.equal(fs.existsSync(path.join(data,'.local/case-memory-runtime/installed.json')),false);
  assert.ok(!JSON.stringify(runtime.status()).includes('synthetic-secret'));await runtime.stop();
});
test('a running process with failed readiness is not reported as ready, and shutdown closes only the owned child',async t=>{
  const data=fixture(t),broken=path.join(data,'synthetic-unhealthy');
  const runtime=await createCaseMemoryRuntime({data,payload:data,python:process.execPath,secret:'synthetic-secret',spawnProcess(command,args,options){
    if(args.includes('--stop-database'))return spawn(process.execPath,['-e','process.exit(0)'],{stdio:'ignore'});
    const program=`const fs=require('fs'),http=require('http');const server=http.createServer((req,res)=>{if(req.headers.authorization!=='Bearer '+process.env.QX_MEMORY_SERVICE_TOKEN){res.writeHead(403).end();return;}res.writeHead(req.url.startsWith('/health')&&fs.existsSync(${JSON.stringify(broken)})?503:200,{'content-type':'application/json'}).end('{"banks":[]}')});server.listen(Number(process.env.QX_MEMORY_SERVICE_PORT),'127.0.0.1');process.stdin.once('data',()=>server.close(()=>process.exit(0)));`;
    return spawn(process.execPath,['-e',program],options);
  }});t.after(()=>runtime.stop());
  const directory=path.join(data,'.local/case-memory-runtime');
  const interpreter=path.join(directory,'venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');fs.mkdirSync(path.dirname(interpreter),{recursive:true});fs.writeFileSync(interpreter,'synthetic');fs.writeFileSync(path.join(directory,'installed.json'),JSON.stringify({version:'1.2.0'}));
  await runtime.prepare();assert.equal(runtime.status().phase,'ready');fs.writeFileSync(broken,'synthetic');
  const status=await (await fetch(runtime.env.QX_CASE_MEMORY_CONTROL_URL+'/status',{headers:{Authorization:`Bearer ${runtime.env.QX_CASE_MEMORY_CONTROL_TOKEN}`}})).json();
  assert.equal(status.phase,'error');await runtime.stop();
});
