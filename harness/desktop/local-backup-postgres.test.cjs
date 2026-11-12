const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const crypto=require('node:crypto');
const {createLocalBackup,restoreLocalBackup,reviewLocalRestore}=require('./local-backup.cjs');
const {python,restic,pgTools}={python:process.env.QX_TEST_PYTHON,restic:process.env.QX_TEST_RESTIC,pgTools:process.env.QX_TEST_PG_TOOLS};
test('cold PostgreSQL identity, records, vector index and empty directories survive encrypted restore',{
  skip:process.platform!=='win32'||!python||!restic||!pgTools,
},async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-pg-backup-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const data=path.join(root,'source'),bundle=path.join(root,'backup'),destination=path.join(root,'restored');
  fs.mkdirSync(path.join(data,'workspace'),{recursive:true});fs.mkdirSync(path.join(data,'.local'));
  for(const [name,value] of Object.entries({'initialized-payload.json':{schema:2,data},'runtime.json':{hostPid:null,launcherPid:123},'host-state.json':{phase:'stopped',hostPid:null,launcherPid:123}}))
    fs.writeFileSync(path.join(data,'.local',name),JSON.stringify(value));
  function fixture(action,target){
    const result=spawnSync(python,[path.join(__dirname,'../tests/pg-backup-fixture.py'),action,target,pgTools],{encoding:'utf8',windowsHide:true,timeout:120000});
    assert.equal(result.status,0,result.stderr);return JSON.parse(result.stdout);
  }
  const expected=fixture('seed',data);
  const options={data,bundle,destination,python,restic,pgTools,password:'synthetic-backup-passphrase'};
  const cluster=path.join(data,'.local/case-memory-runtime/database');
  fs.mkdirSync(path.join(cluster,'log'),{recursive:true});
  fs.writeFileSync(path.join(cluster,'log','synthetic.db'),'opaque synthetic PostgreSQL log');
  function fileHashes(){
    return Object.fromEntries(fs.readdirSync(cluster,{recursive:true,withFileTypes:true}).filter(e=>e.isFile()).map(e=>{
      const file=path.join(e.parentPath,e.name);return [path.relative(cluster,file),crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')];
    }));
  }
  const before=fileHashes();
  const saved=await createLocalBackup(options);
  assert.equal(saved.applicationComplete,false);assert.equal(saved.postgresIncluded,true);
  assert.deepEqual(fileHashes(),before);
  await t.test('missing PostgreSQL tools refuse restore before plaintext staging',async()=>{
    await assert.rejects(restoreLocalBackup({...options,pgTools:undefined}),{code:'BACKUP_POSTGRES_TOOLS_REQUIRED'});
    assert.equal(fs.existsSync(destination),false);
  });
  const restored=await restoreLocalBackup(options);
  assert.equal(restored.activation,'manual-review-required');
  const review=await reviewLocalRestore({destination,python,pgTools});
  assert.equal(review.postgresIncluded,true);assert.equal(review.activation,'blocked');
  assert.ok(review.blockers.includes('postgres-instance-registration'));assert.ok(review.blockers.includes('hindsight-api-validation'));
  assert.equal(fs.existsSync(path.join(destination,'.local/case-memory-runtime/database/postmaster.pid')),false);
  assert.deepEqual(fixture('verify',destination),expected);
  assert.equal(fs.readFileSync(path.join(destination,'.local/case-memory-runtime/database/log/synthetic.db'),'utf8'),'opaque synthetic PostgreSQL log');
  assert.deepEqual(fs.readFileSync(path.join(destination,'.local/case-memory-runtime/instance.json')),fs.readFileSync(path.join(data,'.local/case-memory-runtime/instance.json')));
  async function rejectsWithMutation(file,bytes,code){
    const old=fs.existsSync(file)?fs.readFileSync(file):null;
    fs.writeFileSync(file,bytes);
    try{
      await assert.rejects(createLocalBackup({...options,bundle:path.join(root,'rejected')}),{code});
      assert.equal(fs.existsSync(path.join(root,'rejected')),false);
      assert.equal(fs.readdirSync(root).some(name=>name.startsWith('.qx-')),false);
    }finally{if(old===null)fs.unlinkSync(file);else fs.writeFileSync(file,old);}
  }
  await t.test('residual PID and recovery signals cannot be copied as cold data',async()=>{
    await rejectsWithMutation(path.join(cluster,'postmaster.pid'),'123\n','BACKUP_MEMORY_NOT_STOPPED');
    await rejectsWithMutation(path.join(cluster,'standby.signal'),'','BACKUP_POSTGRES_NOT_COLD');
  });
  await t.test('unsupported major and invalid instance identity block completion',async()=>{
    await rejectsWithMutation(path.join(cluster,'PG_VERSION'),'17\n','BACKUP_POSTGRES_VERSION_UNSUPPORTED');
    await rejectsWithMutation(path.join(data,'.local/case-memory-runtime/instance.json'),'{}','BACKUP_POSTGRES_IDENTITY_INVALID');
  });
  await t.test('damaged control and data pages fail native checks without a receipt',async()=>{
    const controlFile=path.join(cluster,'global','pg_control'),control=fs.readFileSync(controlFile);control[100]^=1;
    await rejectsWithMutation(controlFile,control,'BACKUP_POSTGRES_CHECK_FAILED');
    const relation=fs.readdirSync(path.join(cluster,'base'),{recursive:true,withFileTypes:true}).find(e=>e.isFile()&&/^\d+$/.test(e.name)&&fs.statSync(path.join(e.parentPath,e.name)).size>=8192);
    assert.ok(relation);const file=path.join(relation.parentPath,relation.name),damaged=fs.readFileSync(file);damaged[8191]^=1;
    await rejectsWithMutation(file,damaged,'BACKUP_POSTGRES_CHECK_FAILED');
  });
  await t.test('an absent pinned engine is rejected and staging is cleaned',async()=>{
    const emptyTools=path.join(root,'wrong-tools');fs.mkdirSync(emptyTools);
    await assert.rejects(createLocalBackup({...options,bundle:path.join(root,'bad-tools'),pgTools:emptyTools}),{code:'BACKUP_POSTGRES_TOOLS_UNVERIFIED'});
    assert.equal(fs.existsSync(path.join(root,'bad-tools')),false);
  });
  await t.test('missing or damaged checkpoint WAL blocks completion',async()=>{
    const walDir=path.join(cluster,'pg_wal');
    const segments=fs.readdirSync(walDir).filter(n=>/^[0-9A-F]{24}$/.test(n));
    assert.ok(segments.length);
    const copies=segments.map(n=>[path.join(walDir,n),fs.readFileSync(path.join(walDir,n))]);
    for(const [file] of copies)fs.unlinkSync(file);
    try{
      await assert.rejects(createLocalBackup({...options,bundle:path.join(root,'missing-wal')}),{code:'BACKUP_POSTGRES_CHECK_FAILED'});
      assert.equal(fs.existsSync(path.join(root,'missing-wal')),false);
    }finally{for(const [file,bytes] of copies)fs.writeFileSync(file,bytes);}
    assert.equal(copies.length,1,'small synthetic fixture should use one WAL segment');
    const [file,bytes]=copies[0];
    await rejectsWithMutation(file,Buffer.alloc(bytes.length),'BACKUP_POSTGRES_CHECK_FAILED');
    const foreign=Buffer.from(bytes);foreign[24]^=1;
    await rejectsWithMutation(file,foreign,'BACKUP_POSTGRES_CHECK_FAILED');
    const result=spawnSync(path.join(pgTools,'bin/pg_controldata.exe'),[cluster],{encoding:'utf8',windowsHide:true,env:{...process.env,LC_ALL:'C'}});
    assert.equal(result.status,0,result.stderr);
    const checkpoint=result.stdout.match(/Latest checkpoint location:\s*([0-9A-F]+)\/([0-9A-F]+)/);
    assert.ok(checkpoint);const offset=Number((BigInt('0x'+checkpoint[1])*0x100000000n+BigInt('0x'+checkpoint[2]))%BigInt(bytes.length));
    const damaged=Buffer.from(bytes);damaged[offset+24]^=1;
    await rejectsWithMutation(file,damaged,'BACKUP_POSTGRES_CHECK_FAILED');
  });
  assert.equal(fs.readdirSync(root).some(name=>name.startsWith('.qx-')),false);
});
