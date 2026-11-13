const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawn,spawnSync}=require('node:child_process');
const {createCaseMemoryRuntime,buildServiceEnvironment}=require('./case-memory-runtime.cjs');
const {createLocalBackup,restoreLocalBackup}=require('./local-backup.cjs');
const python=process.env.QX_TEST_PYTHON,pgTools=process.env.QX_TEST_PG_TOOLS,pgModule=process.env.QX_TEST_PG0_MODULE,restic=process.env.QX_TEST_RESTIC;

test('native pg0 keeps source and restored identity separate through restart and rejected registration cleanup',{
  skip:process.platform!=='win32'||!python||!pgTools||!pgModule||!restic,timeout:180000,
},async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-memory-binding-')),source=path.join(root,'source'),destination=path.join(root,'restored'),activeCopy=path.join(root,'activation-fixture');
  const runtimes=[],registrations=[],errors=new Map();
  t.after(async()=>{
    for(const runtime of runtimes)await runtime.stop();
    for(const file of registrations){
      if(!fs.existsSync(file))continue;
      const info=JSON.parse(fs.readFileSync(file,'utf8'));
      assert.ok(path.resolve(info.data_dir).startsWith(root+path.sep));
      assert.equal(fs.existsSync(path.join(info.data_dir,'postmaster.pid')),false);
      fs.unlinkSync(file);fs.rmdirSync(path.dirname(file));
    }
    fs.rmSync(root,{recursive:true,force:true});
  });
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(pgModule,'pg0/bin/pg0.exe'))).digest('hex'),require('../config/postgres-backup-runtime.json').pg0ExeSha256);
  const seeded=spawnSync(python,[path.join(__dirname,'../tests/pg-backup-fixture.py'),'seed',source,pgTools],{encoding:'utf8',windowsHide:true,timeout:60000});
  assert.equal(seeded.status,0,seeded.stderr);const expected=JSON.parse(seeded.stdout);
  fs.mkdirSync(path.join(source,'workspace'));
  for(const [name,value] of Object.entries({'initialized-payload.json':{schema:2,data:source},'runtime.json':{hostPid:null,launcherPid:123},'host-state.json':{phase:'stopped',hostPid:null,launcherPid:123}}))fs.writeFileSync(path.join(source,'.local',name),JSON.stringify(value));
  const options={data:source,destination,bundle:path.join(root,'backup'),python,restic,pgTools,password:'synthetic-memory-binding-only'};
  await createLocalBackup(options);await restoreLocalBackup(options);
  await assert.rejects(createCaseMemoryRuntime({data:destination,payload:root}),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
  // Explicit synthetic activation fixture; the recovered copy and its review markers remain untouched.
  fs.cpSync(path.join(destination,'.local/case-memory-runtime'),path.join(activeCopy,'.local/case-memory-runtime'),{recursive:true});
  const modules=path.join(root,'modules'),app=path.join(modules,'hindsight_api');fs.mkdirSync(app,{recursive:true});
  fs.writeFileSync(path.join(app,'__init__.py'),'');fs.copyFileSync(path.join(__dirname,'../tests/memory-pg0-app.py'),path.join(app,'server.py'));
  function registration(data){
    const directory=fs.realpathSync.native(path.join(data,'.local/case-memory-runtime')),instance=JSON.parse(fs.readFileSync(path.join(directory,'instance.json'),'utf8'));
    const env=buildServiceEnvironment({root:directory,instance,secret:'synthetic',token:'synthetic',port:0,model:'synthetic'});
    return path.join(path.dirname(path.dirname(pgTools)),'instances',new URL(env.HINDSIGHT_API_DATABASE_URL).hostname,'instance.json');
  }
  for(const data of [source,activeCopy]){const file=registration(data);assert.equal(fs.existsSync(file),false);registrations.push(file);}
  assert.notEqual(registrations[0],registrations[1]);
  async function start(data){
    const stderr=[];
    const directory=path.join(data,'.local/case-memory-runtime'),interpreter=path.join(directory,'venv/Scripts/python.exe');
    fs.mkdirSync(path.dirname(interpreter),{recursive:true});fs.writeFileSync(interpreter,'synthetic interpreter marker');fs.writeFileSync(path.join(directory,'installed.json'),JSON.stringify({version:'1.2.0'}));
    const runtime=await createCaseMemoryRuntime({data,payload:root,secret:'synthetic',startupTimeoutMs:30000,spawnProcess(command,args,options){
      const child=spawn(python,args,{...options,env:{...options.env,PYTHONPATH:[modules,pgModule,process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),TEST_PG_TOOLS:pgTools}});
      child.stderr?.on('data',chunk=>stderr.push(String(chunk)));return child;
    }});runtimes.push(runtime);errors.set(runtime,stderr);await runtime.prepare();return runtime;
  }
  async function read(runtime){
    assert.equal(runtime.status().phase,'ready',(errors.get(runtime)||[]).join('').replaceAll('ab'.repeat(32),'[synthetic-password]').slice(-4000));
    const response=await fetch(runtime.env.QX_HINDSIGHT_URL+'/v1/default/banks',{headers:{Authorization:'Bearer '+runtime.env.QX_HINDSIGHT_TOKEN}});
    assert.equal(response.status,200);return response.json();
  }
  const original=await start(source),copy=await start(activeCopy);
  const value=await read(original);assert.deepEqual(value,{records:40,groups:2,content:'虚构记忆-3',system:expected.systemIdentifier});assert.deepEqual(await read(copy),value);
  await t.test('an owned database with failed health authentication still shuts down',async()=>{
    const bytes=fs.readFileSync(registrations[1]),info=JSON.parse(bytes);info.password='synthetic-invalid-password';fs.writeFileSync(registrations[1],JSON.stringify(info));
    try{await copy.stop();assert.equal(fs.existsSync(path.join(activeCopy,'.local/case-memory-runtime/database/postmaster.pid')),false);}
    finally{
      fs.writeFileSync(registrations[1],bytes);
      if(fs.existsSync(path.join(activeCopy,'.local/case-memory-runtime/database/postmaster.pid'))){const rescue=await start(activeCopy);await rescue.stop();}
    }
  });
  assert.deepEqual(await read(original),value);
  assert.equal(fs.existsSync(path.join(activeCopy,'.local/case-memory-runtime/database/postmaster.pid')),false);
  const saved=fs.readFileSync(registrations[1]);
  for(const fault of ['foreign','unreadable'])await t.test(fault,async()=>{
    fs.writeFileSync(registrations[1],fault==='foreign'?fs.readFileSync(registrations[0]):'{invalid synthetic registration');
    try{const refused=await start(activeCopy);assert.equal(refused.status().phase,'error');await refused.stop();assert.deepEqual(await read(original),value);}
    finally{fs.writeFileSync(registrations[1],saved);}
  });
  const restarted=await start(activeCopy);assert.deepEqual(await read(restarted),value);await restarted.stop();
  await t.test('damaged running registration reports unconfirmed shutdown and can retry after repair',async()=>{
    const bytes=fs.readFileSync(registrations[0]);fs.writeFileSync(registrations[0],'{invalid synthetic registration');
    try{
      await assert.rejects(original.stop(),/shutdown could not be verified/);
      assert.equal(original.status().phase,'error');assert.equal(fs.existsSync(path.join(source,'.local/case-memory-runtime/owner.json')),true);
      await assert.rejects(fetch(original.env.QX_CASE_MEMORY_CONTROL_URL+'/status'));
    }finally{
      fs.writeFileSync(registrations[0],bytes);await original.stop();
      if(fs.existsSync(path.join(source,'.local/case-memory-runtime/database/postmaster.pid'))){const rescue=await start(source);await rescue.stop();}
    }
  });
  assert.equal(fs.existsSync(path.join(source,'.local/case-memory-runtime/database/postmaster.pid')),false);
  assert.equal(fs.existsSync(path.join(destination,'backup-manifest.json')),true);
});
