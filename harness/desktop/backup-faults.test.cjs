// Opt-in native fault integration. Interception exists only in this test's child process.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const childProcess=require('node:child_process');
const assert=require('node:assert/strict');
const put=(file,value)=>{fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n');};
const read=file=>JSON.parse(fs.readFileSync(file,'utf8'));
const digest=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function files(root){
 const result={};
 function visit(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
  const file=path.join(dir,entry.name);
  if(entry.isSymbolicLink())result[path.relative(root,file)]={link:fs.readlinkSync(file)};
  else if(entry.isDirectory())visit(file);
  else result[path.relative(root,file)]={sha256:digest(file),mtimeNs:fs.statSync(file,{bigint:true}).mtimeNs.toString()};
 }}
 visit(root);return result;
}
function payloadFixture(root,fixed){
 const payload=path.join(root,'payload'),source=path.resolve(__dirname,'..'),stage=require('../packaging/stage.cjs'),manifest=[];
 fs.mkdirSync(payload);
 for(const folder of ['bridge','plugins','legacy','workspace-seed']){fs.mkdirSync(path.join(payload,folder));stage.overlay(path.join(source,folder),path.join(payload,folder),manifest,folder);}
 fs.mkdirSync(path.join(payload,'config'));stage.overlay(path.join(source,'packaging/payload-config'),path.join(payload,'config'),manifest,'config');
 stage.copyBackupConfiguration(source,payload,manifest);stage.copyDesktopRunners(source,payload,manifest);
 fs.mkdirSync(path.join(payload,'runtime'));fs.copyFileSync(path.join(fixed,'runtime/node.exe'),path.join(payload,'runtime/node.exe'));
 fs.cpSync(path.dirname(process.env.QX_TEST_PYTHON),path.join(payload,'runtime/python'),{recursive:true,filter:file=>!file.includes('__pycache__')});
 fs.symlinkSync(path.join(fixed,'node_modules'),path.join(payload,'node_modules'),'junction');
 put(path.join(payload,'config/initialization.json'),{schema:1,id:crypto.createHash('sha256').update(JSON.stringify(manifest)).digest('hex')});
 return payload;
}
async function faultChild(requestFile){
 const request=read(requestFile),{boundary,options}=request;
 const freeze=details=>{
  put(request.event,{boundary,pid:process.pid,at:new Date().toISOString(),...details});
  // Parent verifies this process identity before terminating the process tree.
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0);
 };
 const spawn=childProcess.spawn;
 childProcess.spawn=function(exe,args,settings){
  if(boundary==='backup-snapshot'&&args.includes('init'))freeze({snapshot:path.join(settings.cwd,'snapshot'),bundle:options.bundle});
  if(boundary==='backup-engine-failure'&&args.includes('backup')){
   put(request.event,{boundary,pid:process.pid,snapshot:path.join(settings.cwd,'snapshot'),bundle:options.bundle,repositoryInitialized:fs.existsSync(path.join(options.bundle,'repository/config'))});
   return spawn.call(this,exe,[...args,'--synthetic-invalid-option'],settings);
  }
  const child=spawn.apply(this,arguments),end=child.stdin?.end;
  if(end&&args.some(arg=>String(arg).endsWith('backup_snapshot.py'))){
   child.stdin.end=function(input,...rest){
    const job=JSON.parse(input);
    if(job.action==='publish'){
     if(boundary==='restore-publish'||boundary==='activation-publish')freeze({workerPid:child.pid,staged:job.source,target:job.target});
     if(boundary==='publish-worker-failure'){
      put(request.event,{boundary,pid:process.pid,workerPid:child.pid,staged:job.source,target:job.target});
      return end.call(this,JSON.stringify({action:'synthetic-unsupported-action'}),...rest);
     }
    }
    return end.call(this,input,...rest);
   };
  }
  return child;
 };
 const rename=fs.renameSync;
 fs.renameSync=function(from,to){
  if(boundary==='initialize-ready'&&path.resolve(to)===path.join(options.destination,'.local/restore-activation.json'))freeze({temporary:from,target:to});
  if(boundary==='selection-rename'&&path.resolve(to)===path.join(options.data,'.local/data-location.json'))freeze({temporary:from,target:to});
  return rename.apply(this,arguments);
 };
 if(boundary==='initialize-start')freeze({target:options.destination});
 const api={
  backup:()=>require('./local-backup.cjs').createLocalBackup(options),
  restore:()=>require('./local-backup.cjs').restoreLocalBackup(options),
  prepare:()=>require('./restore-activation.cjs').prepareRestoreActivation(options),
  initialize:()=>require('./installed-runtime.cjs').initializePreparedRestore(options.payload,options.destination),
  select:()=>require('./data-location.cjs').selectDataLocation(options.data,options.destination),
 };
 try{const result=await api[request.action]();put(request.result,{ok:true,result});}
 catch(error){put(request.result,{ok:false,error:error.code||error.message});process.exitCode=1;}
}
if(process.argv[2]==='--fault-child'){
 faultChild(process.argv[3]).catch(error=>{console.error(error);process.exitCode=1;});
}else{
 const {test}=require('node:test');
 const enabled=process.platform==='win32'&&process.env.QX_BACKUP_FAULTS==='1';
 test('native interrupted backup, restore, preparation and selection preserve originals and permit fresh retries',{skip:!enabled,timeout:600000},async t=>{
  const evidence=process.env.QX_BACKUP_FAULTS_EVIDENCE;
  assert.ok(evidence&&path.isAbsolute(evidence),'Set an absolute QX_BACKUP_FAULTS_EVIDENCE directory');
  for(const key of ['QX_TEST_APP','QX_TEST_PYTHON','QX_TEST_RESTIC'])assert.ok(process.env[key]&&fs.existsSync(process.env[key]),key);
  fs.mkdirSync(evidence,{recursive:true});
  const root=fs.mkdtempSync(path.join(evidence,'fault-fixture-')),data=path.join(root,'original'),payload=payloadFixture(root,path.resolve(process.env.QX_TEST_APP));
  const temp=path.join(root,'temp');fs.mkdirSync(temp);
  const common={data,payload,python:path.resolve(process.env.QX_TEST_PYTHON),restic:path.resolve(process.env.QX_TEST_RESTIC),password:'synthetic-fault-tests-only-2026'};
  const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>['systemroot','windir','path','pathext','userprofile','localappdata','appdata','node_path'].includes(key.toLowerCase())));
  Object.assign(env,{TEMP:temp,TMP:temp,PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8'});
  const summary={root,node:process.version,syntheticOnly:true,modelRequests:0,externalMessages:0,physicalPowerLoss:false,checkpoints:[]};
  const checkpoint=(name,details={})=>{summary.checkpoints.push({name,at:new Date().toISOString(),...details});put(path.join(root,'summary.json'),summary);};
  t.after(()=>{if(summary.result!=='passed')summary.result='failed';checkpoint('test-finished');});
  async function scenario(name,run){
   let failure;
   await t.test(name,async()=>{try{await run();}catch(error){failure=error;summary.result='failed';checkpoint('scenario-failed',{scenario:name,error:error.code||error.message});throw error;}});
   if(failure)throw failure;
  }
  const local=require('./local-backup.cjs'),activation=require('./restore-activation.cjs'),installed=require('./installed-runtime.cjs'),locations=require('./data-location.cjs'),stop=require('./installed-stop.cjs');
  put(path.join(data,'workspace/synthetic-material.txt'),{text:'合成原件：任何中断不得修改。'});
  put(path.join(data,'.local/desktop-data/locale.json'),{locale:'zh-CN'});
  put(path.join(data,'.local/initialized-payload.json'),{schema:2,data});
  put(path.join(data,'.local/runtime.json'),{hostPid:null,launcherPid:process.pid});
  put(path.join(data,'.local/host-state.json'),{phase:'stopped',hostPid:null,launcherPid:process.pid});
  const seed=childProcess.spawnSync(common.python,['-c',"import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('CREATE TABLE synthetic (id INTEGER PRIMARY KEY, text TEXT)'); c.execute('INSERT INTO synthetic VALUES (1, ?)',['synthetic recoverable row']); c.commit(); c.close()",path.join(data,'workspace/synthetic.sqlite')],{env,encoding:'utf8',windowsHide:true});
  assert.equal(seed.status,0,seed.stderr);locations.returnToOriginalData(data);
  const protectedState=()=>Object.fromEntries(require('./backup-preparation.cjs').inspectScope(data).files.map(item=>[item.path,{sha256:digest(path.join(data,item.path)),mtimeNs:fs.statSync(path.join(data,item.path),{bigint:true}).mtimeNs.toString()}]));
  const original=protectedState(),selector=path.join(data,'.local/data-location.json'),selectorOriginal=fs.readFileSync(selector),selectorTime=fs.statSync(selector,{bigint:true}).mtimeNs.toString();
  put(path.join(root,'original-before.json'),original);
  const unchanged=()=>{const after=protectedState();put(path.join(root,'original-after.json'),after);assert.deepEqual(after,original);};
  const unchangedSelector=()=>{assert.deepEqual(fs.readFileSync(selector),selectorOriginal);assert.equal(fs.statSync(selector,{bigint:true}).mtimeNs.toString(),selectorTime);assert.equal(locations.resolveDataLocation(data).data,data);};
  async function leaseAvailable(target){const lease=await stop.claimLauncher(target);await lease.close();}
  function blocked(target){
   const before=files(target);
   assert.throws(()=>installed.initialize(payload,target),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
   assert.throws(()=>locations.selectDataLocation(data,target),{code:'LOCATION_RESTORE_NOT_READY'});
   assert.deepEqual(files(target),before);unchangedSelector();
  }
  async function runChild(action,boundary,options,{kill=true}={}){
   const folder=path.join(root,boundary);fs.mkdirSync(folder);
   const requestFile=path.join(folder,'request.json'),event=path.join(folder,'event.json'),result=path.join(folder,'result.json');
   put(requestFile,{action,boundary,options,event,result});
   const stdout=fs.openSync(path.join(folder,'stdout.log'),'w'),stderr=fs.openSync(path.join(folder,'stderr.log'),'w');
   const child=childProcess.spawn(process.execPath,[__filename,'--fault-child',requestFile],{env,cwd:root,windowsHide:true,stdio:['ignore',stdout,stderr]});
   fs.closeSync(stdout);fs.closeSync(stderr);
   let finished=false;const exit=new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',(code,signal)=>{finished=true;resolve({code,signal});});});
   const terminate=()=>{
    assert.equal(finished,false,'fault child already exited');
    const inspect=childProcess.spawnSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',`$p=Get-CimInstance Win32_Process -Filter "ProcessId = ${child.pid}" -ErrorAction Stop; $p | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress`],{encoding:'utf8',windowsHide:true,timeout:15000});
    assert.equal(inspect.status,0,inspect.stderr);const identity=JSON.parse(inspect.stdout);
    assert.equal(identity.ParentProcessId,process.pid);assert.equal(path.resolve(identity.ExecutablePath).toLowerCase(),process.execPath.toLowerCase());
    assert.ok(identity.CommandLine.includes(requestFile));assert.ok(identity.CommandLine.includes('--fault-child'));
    put(path.join(folder,'verified-process.json'),identity);
    const terminated=childProcess.spawnSync('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{encoding:'utf8',windowsHide:true,timeout:15000});
    put(path.join(folder,'termination.json'),{status:terminated.status,stdout:terminated.stdout,stderr:terminated.stderr});assert.equal(terminated.status,0,terminated.stderr);
   };
   try{
    const deadline=Date.now()+90000;
    while(!fs.existsSync(event)&&!finished&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,30));
    assert.equal(fs.existsSync(event),true,'boundary not reached: '+boundary+' '+(fs.existsSync(result)?JSON.stringify(read(result)):''));
    const observed=read(event);assert.equal(observed.pid,child.pid);
    if(kill){
     if(boundary==='backup-snapshot')await assert.rejects(require('./backup-preparation.cjs').prepareBackup(data),{code:'BACKUP_HOST_BUSY'});
     terminate();
    }
    const ended=await exit;put(path.join(folder,'exit.json'),ended);
    if(kill){assert.notEqual(ended.code,0);assert.equal(fs.existsSync(result),false,'abrupt stop must bypass ordinary completion');if(observed.workerPid)assert.equal(stop.processAlive(observed.workerPid),false,'owned worker must terminate with its parent');}
    else{assert.equal(ended.code,1);assert.deepEqual(read(result),{ok:false,error:boundary==='backup-engine-failure'?'BACKUP_ENGINE_FAILED':'BACKUP_INVALID_ACTION'});}
    checkpoint(boundary,{...observed,exit:ended,injectedFailure:!kill});return observed;
   }finally{if(!finished){terminate();await exit;}}
  }
  const bundle=path.join(root,'complete-backup');
  await scenario('terminated backup retains an incomplete bundle, leaves originals unchanged and releases the OS lease',async()=>{
   const abandoned=path.join(root,'incomplete-backup');
   const observed=await runChild('backup','backup-snapshot',{...common,bundle:abandoned});
   assert.equal(fs.existsSync(path.join(abandoned,'completed.json')),false);blocked(observed.snapshot);
   await assert.rejects(local.restoreLocalBackup({...common,bundle:abandoned,destination:path.join(root,'cannot-restore-incomplete')}));
   assert.equal(fs.existsSync(path.join(root,'cannot-restore-incomplete')),false);
   await assert.rejects(local.createLocalBackup({...common,bundle:abandoned}),{code:'BACKUP_TARGET_EXISTS'});
   await leaseAvailable(data);unchanged();unchangedSelector();
   const receipt=await local.createLocalBackup({...common,bundle});assert.equal(receipt.fileCount,3);assert.equal(receipt.databaseCount,1);
   checkpoint('backup-new-directory-retry',{bundle,receipt});
  });
  await scenario('nonzero restic backup cleans its partial repository and a fresh backup succeeds',async()=>{
   const failedBundle=path.join(root,'failed-engine-bundle'),before=fs.readdirSync(root).filter(name=>name.startsWith('.qx-backup-')).sort(),saved=files(bundle);
   const observed=await runChild('backup','backup-engine-failure',{...common,bundle:failedBundle},{kill:false});
   assert.equal(observed.repositoryInitialized,true);assert.equal(fs.existsSync(failedBundle),false);
   assert.deepEqual(fs.readdirSync(root).filter(name=>name.startsWith('.qx-backup-')).sort(),before);assert.deepEqual(files(bundle),saved);unchanged();unchangedSelector();await leaseAvailable(data);
   const retry=path.join(root,'engine-failure-retry-backup'),receipt=await local.createLocalBackup({...common,bundle:retry});
   assert.equal(receipt.fileCount,3);assert.equal(receipt.databaseCount,1);checkpoint('engine-failure-new-directory-retry',{bundle:retry});
  });
  const backupBefore=files(bundle),reviewRoot=path.join(root,'review-copy');let reviewBefore,review;
  await scenario('termination before restore publication exposes no destination and retains an inactive staged copy',async()=>{
   const destination=path.join(root,'unpublished-restore'),observed=await runChild('restore','restore-publish',{...common,bundle,destination});
   assert.equal(fs.existsSync(destination),false);blocked(observed.staged);unchanged();assert.deepEqual(files(bundle),backupBefore);
   await local.restoreLocalBackup({...common,bundle,destination:reviewRoot});blocked(reviewRoot);reviewBefore=files(reviewRoot);
   review=await activation.inspectRestoreActivation({...common,root:reviewRoot});checkpoint('restore-new-directory-retry',{reviewRoot,counts:review.counts});
  });
  const prepare=destination=>activation.prepareRestoreActivation({...common,root:reviewRoot,destination,reviewToken:review.reviewToken,applySettings:true});
  await scenario('termination before preparation publication cannot initialize or select the staged copy',async()=>{
   const destination=path.join(root,'unpublished-activation'),observed=await runChild('prepare','activation-publish',{...common,root:reviewRoot,destination,reviewToken:review.reviewToken,applySettings:true});
   assert.equal(fs.existsSync(destination),false);blocked(observed.staged);await leaseAvailable(destination);
   assert.deepEqual(files(reviewRoot),reviewBefore);unchanged();
   const retry=path.join(root,'prepared-after-publish-stop');await prepare(retry);blocked(retry);checkpoint('prepare-new-directory-retry',{destination:retry});
  });
  await scenario('prepared copy remains inactive when its initializer is terminated before starting',async()=>{
   const destination=path.join(root,'prepared-before-init');await prepare(destination);const before=files(destination);
   await runChild('initialize','initialize-start',{...common,destination});assert.deepEqual(files(destination),before);blocked(destination);unchanged();
   const retry=path.join(root,'retry-before-init');await prepare(retry);await installed.initializePreparedRestore(payload,retry);assert.equal(read(path.join(retry,'.local/restore-activation.json')).phase,'ready');
   unchangedSelector();checkpoint('initialization-new-directory-retry',{destination:retry});
  });
  let ready;
  await scenario('interrupted initialization never marks its partially initialized copy ready',async()=>{
   const destination=path.join(root,'interrupted-initializer');await prepare(destination);
   const observed=await runChild('initialize','initialize-ready',{...common,destination});
   assert.equal(fs.existsSync(observed.temporary),true);assert.equal(read(path.join(destination,'.local/restore-activation.json')).phase,'prepared');
   assert.equal(read(path.join(destination,'.local/initialized-payload.json')).schema,2);blocked(destination);await leaseAvailable(destination);unchanged();
   ready=path.join(root,'ready-retry');await prepare(ready);await installed.initializePreparedRestore(payload,ready);assert.equal(read(path.join(ready,'.local/restore-activation.json')).phase,'ready');
   unchangedSelector();checkpoint('partial-initialization-new-directory-retry',{destination:ready});
  });
  await scenario('termination between selector temporary write and rename retains the previous complete record',async()=>{
   const observed=await runChild('select','selection-rename',{...common,destination:ready});
   assert.equal(read(observed.temporary).data,ready);unchangedSelector();unchanged();
   locations.selectDataLocation(data,ready);assert.equal(locations.resolveDataLocation(data).data,ready);
   locations.rollbackDataLocation(data);assert.equal(locations.resolveDataLocation(data).data,data);checkpoint('selection-retry-and-rollback',{destination:ready});
  });
  await scenario('nonzero restore worker cleans its owned staging and a fresh restore succeeds',async()=>{
   const destination=path.join(root,'failed-worker-target'),before=fs.readdirSync(root).filter(name=>name.startsWith('.qx-restore-')).sort();
   await runChild('restore','publish-worker-failure',{...common,bundle,destination},{kill:false});
   assert.equal(fs.existsSync(destination),false);assert.deepEqual(fs.readdirSync(root).filter(name=>name.startsWith('.qx-restore-')).sort(),before);
   const retry=path.join(root,'worker-failure-retry');await local.restoreLocalBackup({...common,bundle,destination:retry});
   assert.throws(()=>installed.initialize(payload,retry),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});checkpoint('worker-failure-new-directory-retry',{destination:retry});
  });
  unchanged();assert.deepEqual(files(reviewRoot),reviewBefore);assert.deepEqual(files(bundle),backupBefore);
  summary.result='passed';summary.unchangedOriginalFiles=Object.keys(original).length;
  summary.terminatedProcessTrees=summary.checkpoints.filter(item=>item.exit&&item.injectedFailure===false).length;
  summary.injectedWorkerFailures=summary.checkpoints.filter(item=>item.boundary==='publish-worker-failure').length;
  summary.injectedEngineFailures=summary.checkpoints.filter(item=>item.boundary==='backup-engine-failure').length;
  checkpoint('finished');console.log('Fault evidence: '+path.join(root,'summary.json'));
 });
}
