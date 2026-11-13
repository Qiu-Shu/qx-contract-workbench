const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),http=require('node:http'),crypto=require('node:crypto');
const {spawn,spawnSync}=require('node:child_process');
const {createCaseMemoryRuntime,buildServiceEnvironment}=require('./case-memory-runtime.cjs');
const {createLocalBackup,restoreLocalBackup}=require('./local-backup.cjs');
const python=process.env.QX_TEST_PYTHON,hindsightPython=process.env.QX_TEST_HINDSIGHT_PYTHON,pgTools=process.env.QX_TEST_PG_TOOLS,restic=process.env.QX_TEST_RESTIC;

test('test network boundary allows byte-form loopback names and rejects external DNS before lookup',{skip:!hindsightPython},t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-hindsight-network-')),denials=path.join(root,'denials');
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const result=spawnSync(hindsightPython,['-c',"import socket\nsocket.getaddrinfo(b'127.0.0.1',80)\ntry: socket.getaddrinfo('example.invalid',443)\nexcept PermissionError: pass\nelse: raise AssertionError('External lookup was allowed')"],{encoding:'utf8',windowsHide:true,timeout:15000,env:{...process.env,PYTHONPATH:path.join(__dirname,'../tests/hindsight-loopback'),QX_TEST_NETWORK_DENIALS:denials}});
  assert.equal(result.status,0,result.stderr);assert.equal(fs.readFileSync(denials,'utf8').trim(),'socket.getaddrinfo');
});

test('real Hindsight and source ledger survive cold restore without reindexing or cross-case leakage',{
  skip:process.platform!=='win32'||!python||!hindsightPython||!pgTools||!restic,timeout:300000,
},async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-hindsight-restore-')),source=path.join(root,'source'),destination=path.join(root,'restored'),activeCopy=path.join(root,'synthetic-activation');
  const runtimes=[],registrations=[],networkDenials=path.join(root,'network-denials.log'),providerErrors=[],runtimeLogs=new Map(),runtimeDirectories=new Map();
  let extractions=0,embeddings=0;
  // Only the external model boundary is synthetic; the Hindsight server and database are unmodified.
  const provider=http.createServer(async(request,response)=>{
    try{
      let raw='';for await(const chunk of request)raw+=chunk;
      const body=JSON.parse(raw);let result;
      if(request.url==='/v1/embeddings'){
        embeddings++;const inputs=Array.isArray(body.input)?body.input:[body.input];
        result={object:'list',model:'synthetic-embedding',data:inputs.map((_,index)=>({object:'embedding',index,embedding:[1,...Array(383).fill(0)]})),usage:{prompt_tokens:1,total_tokens:1}};
      }else if(request.url==='/v1/chat/completions'){
        extractions++;const content=JSON.stringify(body.messages);
        const what=['虚构甲案约定周三交付蓝色样品。','虚构乙案约定周五归还绿色设备。','虚构副本新增红色样品。'].find(text=>content.includes(text));
        assert.ok(what,'Unexpected model request');
        result={id:'synthetic',object:'chat.completion',created:1,model:'synthetic-model',choices:[{index:0,finish_reason:'stop',message:{role:'assistant',content:JSON.stringify({facts:[{what,when:'N/A',where:'N/A',who:'N/A',why:'N/A',fact_type:'world',entities:[]}]})}}],usage:{prompt_tokens:1,completion_tokens:1,total_tokens:2}};
      }else throw Error('Unexpected model endpoint');
      response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify(result));
    }catch(error){providerErrors.push(error.message);response.writeHead(500);response.end('{}');}
  });
  await new Promise(resolve=>provider.listen(0,'127.0.0.1',resolve));
  const providerUrl=`http://127.0.0.1:${provider.address().port}/v1`;
  t.after(async()=>{
    const failures=[];
    try{
      for(const runtime of runtimes){try{await runtime.stop();}catch(error){failures.push(error);}}
      for(const file of registrations){
        try{
          if(!fs.existsSync(file))continue;
          const info=JSON.parse(fs.readFileSync(file,'utf8'));
          assert.ok(path.resolve(info.data_dir).startsWith(root+path.sep));
          assert.equal(fs.existsSync(path.join(info.data_dir,'postmaster.pid')),false);
          fs.unlinkSync(file);fs.rmdirSync(path.dirname(file));
        }catch(error){failures.push(error);}
      }
      const denied=fs.existsSync(networkDenials);
      // Keep evidence and any unconfirmed cluster; one failed stop must not strand the others.
      if(!failures.length)fs.rmSync(root,{recursive:true,force:true});
      if(failures.length)throw new AggregateError(failures,'Synthetic runtime cleanup incomplete; directory retained: '+root);
      assert.deepEqual(providerErrors,[]);assert.equal(denied,false,'External Python network attempt');
    }finally{provider.closeAllConnections();await new Promise(resolve=>provider.close(resolve));}
  });
  const version=spawnSync(hindsightPython,['-c','import json,importlib.metadata as m; from pathlib import Path; from alembic.script import ScriptDirectory; import hindsight_api,pg0; assert m.version("hindsight-api-slim")=="1.2.0"; assert m.version("pg0-embedded")=="0.15.2"; print(json.dumps({"module":hindsight_api.__file__,"heads":ScriptDirectory(str(Path(hindsight_api.__file__).parent/"alembic")).get_heads()}))'],{encoding:'utf8',windowsHide:true,timeout:15000,env:{...process.env,PYTHONPATH:'',PYTHONNOUSERSITE:'1'}});
  assert.equal(version.status,0,version.stderr);const pinned=JSON.parse(version.stdout);assert.ok(pinned.module.includes('site-packages'));assert.ok(pinned.heads.length);
  const executable=path.resolve(path.dirname(hindsightPython),'../Lib/site-packages/pg0/bin/pg0.exe');
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),require('../config/postgres-backup-runtime.json').pg0ExeSha256);
  async function start(data){
    const directory=path.join(data,'.local/case-memory-runtime'),marker=path.join(directory,'venv/Scripts/python.exe'),diagnostics=[];
    fs.mkdirSync(path.dirname(marker),{recursive:true});fs.writeFileSync(marker,'test launcher uses the pinned isolated environment');
    fs.writeFileSync(path.join(directory,'installed.json'),JSON.stringify({version:'1.2.0'}));
    const runtime=await createCaseMemoryRuntime({data,payload:root,secret:'synthetic-only',startupTimeoutMs:90000,spawnProcess(command,args,options){
      const child=spawn(hindsightPython,args,{...options,env:{...options.env,
        PYTHONPATH:path.join(__dirname,'../tests/hindsight-loopback'),QX_TEST_NETWORK_DENIALS:networkDenials,
        HINDSIGHT_API_LLM_BASE_URL:providerUrl,HINDSIGHT_API_EMBEDDINGS_PROVIDER:'openai',HINDSIGHT_API_EMBEDDINGS_OPENAI_BASE_URL:providerUrl,
        HINDSIGHT_API_EMBEDDINGS_OPENAI_MODEL:'synthetic-embedding',HINDSIGHT_API_EMBEDDINGS_OPENAI_API_KEY:'synthetic-only',HINDSIGHT_API_EMBEDDINGS_OPENAI_DIMENSIONS:'384',
        HINDSIGHT_API_OTEL_TRACES_ENABLED:'false',HF_HUB_OFFLINE:'1',TRANSFORMERS_OFFLINE:'1',
      }});child.stderr?.on('data',chunk=>diagnostics.push(String(chunk)));child.stdout?.on('data',chunk=>diagnostics.push(String(chunk)));return child;
    }});runtimes.push(runtime);
    const instance=JSON.parse(fs.readFileSync(path.join(directory,'instance.json'),'utf8'));
    const env=buildServiceEnvironment({root:fs.realpathSync.native(directory),instance,secret:'synthetic',token:'synthetic',port:0,model:'synthetic'});
    const registration=path.join(path.dirname(path.dirname(pgTools)),'instances',new URL(env.HINDSIGHT_API_DATABASE_URL).hostname,'instance.json');
    if(!registrations.includes(registration)){assert.equal(fs.existsSync(registration),false);registrations.push(registration);}
    runtimeDirectories.set(runtime,{directory,registration,instance});
    runtimeLogs.set(runtime,()=>diagnostics.join('').replaceAll(instance.databasePassword,'[synthetic-password]').replaceAll(runtime.env.QX_HINDSIGHT_TOKEN,'[test-token]').slice(-9000));
    await runtime.prepare();
    assert.equal(runtime.status().phase,'ready',runtimeLogs.get(runtime)());
    return runtime;
  }
  async function exercise(action,data,runtime,expected=[]){
    return new Promise((resolve,reject)=>{
      const child=spawn(python,[path.join(__dirname,'../tests/hindsight-restore-fixture.py'),action,data],{windowsHide:true,timeout:90000,env:{...process.env,...runtime.env,PYTHONIOENCODING:'utf-8'}});
      let out='',err='';child.stdout.on('data',chunk=>out+=chunk);child.stderr.on('data',chunk=>err+=chunk);
      child.once('error',reject);child.once('close',code=>{if(code)reject(Error(err+'\n'+runtimeLogs.get(runtime)()+'\n'+JSON.stringify({extractions,embeddings,providerErrors})));else{try{resolve(JSON.parse(out));}catch(error){reject(error);}}});child.stdin.end(JSON.stringify(expected));
    });
  }
  async function api(runtime,suffix){
    const response=await fetch(runtime.env.QX_HINDSIGHT_URL+'/v1/default/banks'+suffix,{headers:{Authorization:'Bearer '+runtime.env.QX_HINDSIGHT_TOKEN},signal:AbortSignal.timeout(15000)});
    assert.equal(response.status,200);return response.json();
  }
  async function inventory(runtime){
    const listing=await api(runtime,'');const result=[];
    for(const bank of listing.banks){
      const rows=await api(runtime,`/${bank.bank_id}/memories/list`);
      result.push({bank:bank.bank_id,total:rows.total,items:rows.items.map(row=>({id:row.id,document_id:row.document_id,text:row.text,metadata:row.metadata})).sort((a,b)=>a.id.localeCompare(b.id))});
    }
    return result.sort((a,b)=>a.bank.localeCompare(b.bank));
  }
  function schema(runtime){
    const {directory,registration,instance}=runtimeDirectories.get(runtime),info=JSON.parse(fs.readFileSync(registration,'utf8'));
    assert.equal(path.resolve(info.data_dir),path.resolve(directory,'database'));
    const result=spawnSync(path.join(pgTools,'bin/psql.exe'),['-X','-w','-qAt','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-p',String(info.port),'-U','qx_memory','-d','hindsight'],{
      encoding:'utf8',windowsHide:true,timeout:15000,env:{...process.env,PGPASSWORD:instance.databasePassword,PGCLIENTENCODING:'UTF8'},
      input:"SELECT json_build_object('systemIdentifier',(SELECT system_identifier::text FROM pg_control_system()),'heads',(SELECT json_agg(version_num ORDER BY version_num) FROM alembic_version));",
    });
    assert.equal(result.status,0,result.stderr);const state=JSON.parse(result.stdout);assert.deepEqual(state.heads,pinned.heads.slice().sort());return state;
  }
  fs.mkdirSync(path.join(source,'workspace'),{recursive:true});fs.mkdirSync(path.join(source,'.local'));
  for(const [name,value] of Object.entries({'initialized-payload.json':{schema:2,data:source},'runtime.json':{hostPid:null,launcherPid:123},'host-state.json':{phase:'stopped',hostPid:null,launcherPid:123}}))fs.writeFileSync(path.join(source,'.local',name),JSON.stringify(value));
  const original=await start(source),migrated=schema(original),expected=await exercise('seed',source,original),before=await inventory(original);
  assert.equal(before.length,2);assert.equal(before.reduce((sum,bank)=>sum+bank.total,0),2);assert.ok(extractions>=2);assert.ok(embeddings>=2);
  const extractionCount=extractions;await original.stop();
  const options={data:source,destination,bundle:path.join(root,'backup'),python,restic,pgTools,password:'synthetic-hindsight-restore-only'};
  const saved=await createLocalBackup(options);assert.equal(saved.applicationComplete,false);assert.equal(saved.postgresIncluded,true);
  await restoreLocalBackup(options);
  await assert.rejects(createCaseMemoryRuntime({data:destination,payload:root}),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
  // A test-only copy of reviewed data; never remove guards or activate the delivered restored directory.
  fs.cpSync(path.join(destination,'workspace'),path.join(activeCopy,'workspace'),{recursive:true});
  fs.cpSync(path.join(destination,'.local/case-memory-runtime'),path.join(activeCopy,'.local/case-memory-runtime'),{recursive:true});
  const resumed=await start(source),copy=await start(activeCopy);
  assert.deepEqual(schema(resumed),migrated);assert.deepEqual(schema(copy),migrated);
  assert.deepEqual(await inventory(resumed),before);assert.deepEqual(await inventory(copy),before);
  assert.deepEqual(await exercise('check',source,resumed,expected),expected);assert.deepEqual(await exercise('check',activeCopy,copy,expected),expected);
  assert.equal(extractions,extractionCount,'Restored reads must not reindex');
  await copy.stop();const restarted=await start(activeCopy);
  assert.deepEqual(schema(restarted),migrated);
  assert.deepEqual(await inventory(restarted),before);assert.deepEqual(await exercise('check',activeCopy,restarted,expected),expected);assert.equal(extractions,extractionCount);
  assert.deepEqual(await exercise('append',activeCopy,restarted,expected),{copiedCaseMemoryCount:2});
  assert.equal((await inventory(restarted)).reduce((sum,bank)=>sum+bank.total,0),3);
  assert.deepEqual(await inventory(resumed),before);assert.deepEqual(await exercise('check',source,resumed,expected),expected);
  assert.equal(fs.existsSync(path.join(destination,'backup-manifest.json')),true);
  t.diagnostic(JSON.stringify({cases:2,restoredMemories:2,copyAfterAppend:3,extractions,embeddings,hindsight:'1.2.0',migrationHeads:migrated.heads,model:'loopback synthetic',reindexedOnRead:false}));
});
