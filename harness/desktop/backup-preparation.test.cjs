const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const {claimLauncher}=require('./installed-stop.cjs');

function fixture(t){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-backup-准备-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  fs.mkdirSync(path.join(root,'workspace'));
  fs.mkdirSync(path.join(root,'.local'));
  fs.writeFileSync(path.join(root,'.local/initialized-payload.json'),JSON.stringify({schema:2,data:root}));
  fs.writeFileSync(path.join(root,'.local/runtime.json'),JSON.stringify({hostPid:null,launcherPid:1234}));
  fs.writeFileSync(path.join(root,'.local/host-state.json'),JSON.stringify({hostPid:null,launcherPid:1234,phase:'stopped'}));
  return root;
}
test('backup maintenance refuses a running host, fences a new host, and releases after failure',async t=>{
  const {withBackupPause}=require('./backup-preparation.cjs');
  const data=fixture(t),host=await claimLauncher(data);
  let entered=false;
  try{await assert.rejects(withBackupPause(data,()=>{entered=true}),{code:'BACKUP_HOST_BUSY'});}
  finally{await host.close();}
  assert.equal(entered,false);
  await assert.rejects(withBackupPause(data,async()=>{
    entered=true;
    await assert.rejects(claimLauncher(data),{code:'EADDRINUSE'});
    throw Error('synthetic copy failure');
  }),/synthetic copy failure/);
  assert.equal(entered,true);
  const after=await claimLauncher(data);await after.close();
});
function write(data,name,text='synthetic'){
  const file=path.join(data,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,text);
}
test('preparation inventories business, host and private data without treating credentials or caches as backup files',async t=>{
  const {prepareBackup}=require('./backup-preparation.cjs'),data=fixture(t);
  const business=['workspace/inbox/原件.txt','workspace/.qx-materials/index.sqlite',
    'workspace/knowledge/.qx-materials/index.sqlite','workspace/.qx-media/media.sqlite',
    '.qx-private/uploads/contexts/case/mapping.sqlite','.qx-private/uploads/documents/a/original.txt',
    '.local/dsh-home/sessions/project/session/events.jsonl','.local/dsh-home/storages/workspace.json',
    '.local/layered-knowledge.sqlite','.local/layered-knowledge.sqlite-wal',
    '.local/dsh-home/qx-wechat/qx-pending.json'];
  for(const file of business)write(data,file);
  write(data,'.local/dsh-home/.credentials.yaml','secret-never-emit');
  write(data,'.local/desktop-data/deepseek.bin','synthetic-dpapi');
  write(data,'.local/dsh-home/profiles/web/cordis.patch.yml','synthetic-private-setting');
  write(data,'.local/case-memory-runtime/models/cache.bin');
  write(data,'unrecognized/extra.txt');
  const report=await prepareBackup(data);
  assert.equal(report.backupComplete,false);
  assert.equal(report.scopeReviewRequired,true);
  assert.deepEqual(report.files.filter(f=>f.policy==='protect').map(f=>f.path).sort(),business.sort());
  assert.equal(report.files.some(f=>f.path.endsWith('deepseek.bin')),false);
  assert.equal(report.files.some(f=>f.path.endsWith('cache.bin')),false);
  assert.equal(report.scopes.find(s=>s.path==='.local/dsh-home/.credentials.yaml').policy,'reauthorize');
  assert.equal(report.scopes.find(s=>s.path==='unrecognized').policy,'unclassified');
  assert.equal(JSON.stringify(report).includes('secret-never-emit'),false);
  assert.equal(JSON.stringify(report).includes('synthetic-private-setting'),false);
});
function childResult(args,env={}){
  return new Promise((resolve,reject)=>{
    const child=spawn(process.execPath,args,{env:{...process.env,...env},windowsHide:true,stdio:['ignore','pipe','pipe']});
    let stdout='',stderr='';child.stdout.on('data',chunk=>stdout+=chunk);child.stderr.on('data',chunk=>stderr+=chunk);
    const timer=setTimeout(()=>{child.kill();reject(Error('Synthetic child timed out'));},10000);
    child.once('error',error=>{clearTimeout(timer);reject(error)});
    child.once('close',code=>{clearTimeout(timer);resolve({code,stdout,stderr})});
  });
}
test('the actual installed host cannot initialize during a maintenance window',async t=>{
  const {withBackupPause}=require('./backup-preparation.cjs'),data=fixture(t);
  write(data,'workspace/原件.txt','unchanged');
  await withBackupPause(data,async()=>{
    const result=await childResult([path.join(__dirname,'installed-host.cjs')],{
      QX_INSTALL_DATA:data,QX_PAYLOAD_ROOT:path.join(data,'no-payload-needed'),DEEPSEEK_API_KEY:'synthetic-never-used',
    });
    assert.equal(result.code,1);
    assert.equal(fs.existsSync(path.join(data,'.local/dsh-home')),false,'initialization must not run');
    assert.equal(fs.readFileSync(path.join(data,'workspace/原件.txt'),'utf8'),'unchanged');
    const events=fs.readFileSync(path.join(data,'.local/host-events.jsonl'),'utf8');
    assert.match(events,/launcher_lock_failed/);assert.doesNotMatch(events,/synthetic-never-used/);
  });
  const lock=await claimLauncher(data);await lock.close();
});
test('two preparation calls cannot overlap and owner death releases the OS lease',async t=>{
  const {withBackupPause}=require('./backup-preparation.cjs'),data=fixture(t);
  await withBackupPause(data,async()=>{
    await assert.rejects(withBackupPause(data,()=>assert.fail('overlap')),{code:'BACKUP_HOST_BUSY'});
  });
  const script=`const {withBackupPause}=require(process.argv[1]);withBackupPause(process.argv[2],async()=>{process.send('held');await new Promise(()=>{});}).catch(()=>process.exit(2));`;
  const owner=spawn(process.execPath,['-e',script,path.join(__dirname,'backup-preparation.cjs'),data],{
    windowsHide:true,stdio:['ignore','ignore','ignore','ipc'],
  });
  t.after(()=>{if(owner.exitCode===null)owner.kill()});
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Maintenance owner did not start')),10000);
    owner.once('message',message=>{clearTimeout(timer);assert.equal(message,'held');resolve()});
    owner.once('error',error=>{clearTimeout(timer);reject(error)});
  });
  await assert.rejects(claimLauncher(data),{code:'EADDRINUSE'});
  const closed=new Promise(resolve=>owner.once('close',resolve));owner.kill();await closed;
  const result=await withBackupPause(data,()=>42);assert.equal(result,42);
});
test('missing, mismatched, active and corrupt stop records fail without touching business files',async t=>{
  const {prepareBackup}=require('./backup-preparation.cjs');
  const states=[null,{phase:'running',hostPid:123,launcherPid:1234},
    {phase:'stopping',hostPid:null,launcherPid:1234},{phase:'stopped',hostPid:null,launcherPid:4321},'invalid-json'];
  for(const state of states){
    const data=fixture(t),file=path.join(data,'.local/host-state.json');write(data,'workspace/keep.txt','untouched');
    if(state===null)fs.unlinkSync(file);else fs.writeFileSync(file,state==='invalid-json'?'broken':JSON.stringify(state));
    await assert.rejects(prepareBackup(data),{code:state==='invalid-json'?'BACKUP_INVALID_STATE':'BACKUP_STOP_UNCONFIRMED'});
    assert.equal(fs.readFileSync(path.join(data,'workspace/keep.txt'),'utf8'),'untouched');
    const lease=await claimLauncher(data);await lease.close();
  }
});
test('memory owner or PostgreSQL pid blocks preparation, while cold data and its identity are explicitly classified',async t=>{
  const {prepareBackup}=require('./backup-preparation.cjs'),data=fixture(t);
  for(const name of ['owner.json','database/postmaster.pid']){
    write(data,'.local/case-memory-runtime/'+name,'stale-or-live-is-not-proof-of-stop');
    await assert.rejects(prepareBackup(data),{code:'BACKUP_MEMORY_NOT_STOPPED'});
    fs.unlinkSync(path.join(data,'.local/case-memory-runtime',name));
  }
  write(data,'.local/case-memory-runtime/status.json',JSON.stringify({phase:'ready'}));
  await assert.rejects(prepareBackup(data),{code:'BACKUP_MEMORY_NOT_STOPPED'});
  write(data,'.local/case-memory-runtime/status.json',JSON.stringify({phase:'stopped'}));
  write(data,'.local/case-memory-runtime/database/PG_VERSION','17');
  write(data,'.local/case-memory-runtime/instance.json','{"databasePassword":"synthetic-private"}');
  const report=await prepareBackup(data);
  assert.deepEqual(report.files.filter(f=>f.policy==='cold-postgres').map(f=>f.path),[
    '.local/case-memory-runtime/database/PG_VERSION','.local/case-memory-runtime/instance.json']);
  assert.equal(report.scopeReviewRequired,true);assert.equal(JSON.stringify(report).includes('synthetic-private'),false);
});
test('selected junctions and hard links are rejected without following their targets',async t=>{
  const {prepareBackup}=require('./backup-preparation.cjs'),data=fixture(t),outside=fixture(t);
  write(outside,'workspace/secret.txt','outside');
  const link=path.join(data,'workspace/linked');fs.symlinkSync(path.join(outside,'workspace'),link,'junction');
  await assert.rejects(prepareBackup(data),{code:'BACKUP_LINKED_PATH'});fs.unlinkSync(link);
  const hard=path.join(data,'workspace/hard.txt');fs.linkSync(path.join(outside,'workspace/secret.txt'),hard);
  await assert.rejects(prepareBackup(data),{code:'BACKUP_LINKED_PATH'});
  assert.equal(fs.readFileSync(path.join(outside,'workspace/secret.txt'),'utf8'),'outside');
});
test('command output contains only counts, never filenames, state tokens or credential contents',async t=>{
  const data=fixture(t);write(data,'workspace/合成客户姓名.txt','secret-content');
  write(data,'.local/dsh-home/.credentials.yaml','secret-key');
  const result=await childResult([path.join(__dirname,'../scripts/backup-preflight.cjs'),'--data',data]);
  assert.equal(result.code,0);const report=JSON.parse(result.stdout);assert.equal(report.backupComplete,false);
  assert.equal(report.fileCount,1);assert.equal(report.scopeCounts.reauthorize,1);
  assert.doesNotMatch(result.stdout+result.stderr,/合成客户姓名|secret-content|secret-key/);
});
test('excluded cache and credential links remain visible as requiring review',async t=>{
  const {prepareBackup}=require('./backup-preparation.cjs'),data=fixture(t),outside=fixture(t);
  write(outside,'workspace/do-not-read.txt','outside-secret');
  fs.symlinkSync(path.join(outside,'workspace'),path.join(data,'.local/legal-search-runtime'),'junction');
  fs.mkdirSync(path.join(data,'.local/dsh-home'));
  fs.linkSync(path.join(outside,'workspace/do-not-read.txt'),path.join(data,'.local/dsh-home/.credentials.yaml'));
  const report=await prepareBackup(data);
  assert.equal(report.scopeReviewRequired,true);
  for(const name of ['.local/legal-search-runtime','.local/dsh-home/.credentials.yaml']){
    assert.equal(report.scopes.find(s=>s.path===name).linked,true);
  }
  assert.equal(report.files.length,0);assert.doesNotMatch(JSON.stringify(report),/outside-secret|do-not-read/);
});
