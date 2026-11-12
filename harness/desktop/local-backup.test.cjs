const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const restic=process.env.QX_TEST_RESTIC,python=process.env.QX_TEST_PYTHON;
function fixture(t){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-local-backup-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const data=path.join(root,'source');
  fs.mkdirSync(path.join(data,'workspace'),{recursive:true});fs.mkdirSync(path.join(data,'.local'));
  fs.writeFileSync(path.join(data,'workspace','synthetic.txt'),'synthetic business data');
  fs.writeFileSync(path.join(data,'.local','initialized-payload.json'),JSON.stringify({schema:2,data}));
  fs.writeFileSync(path.join(data,'.local','runtime.json'),JSON.stringify({hostPid:null,launcherPid:123}));
  fs.writeFileSync(path.join(data,'.local','host-state.json'),JSON.stringify({phase:'stopped',hostPid:null,launcherPid:123}));
  return {root,data,bundle:path.join(root,'backup'),destination:path.join(root,'restored'),python,restic,password:'synthetic-passphrase-only-2026'};
}
test('local encrypted backup restores exact business data into a new inactive directory', {skip:process.platform!=='win32'||!python||!restic},async t=>{
  const {createLocalBackup,restoreLocalBackup}=require('./local-backup.cjs');
  const options=fixture(t);
  const seed=spawnSync(python,['-c',`import sys,sqlite3,json,hashlib
from pathlib import Path
from contextlib import closing
r=Path(sys.argv[1])
def write(n,b):
 p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
def database(n,sql,params=()):
 p=r/n;p.parent.mkdir(parents=True,exist_ok=True)
 with closing(sqlite3.connect(p)) as c:
  c.executescript(sql)
  if params:c.execute(*params)
  c.commit()
database('workspace/.qx-materials/index.sqlite','CREATE TABLE materials(path TEXT,size INTEGER,sha256 TEXT);',('INSERT INTO materials VALUES(?,?,?)',('synthetic.txt',23,hashlib.sha256((r/'workspace/synthetic.txt').read_bytes()).hexdigest())))
database('.local/layered-knowledge.sqlite',"CREATE TABLE entries(text TEXT);INSERT INTO entries VALUES('synthetic knowledge');")
database('workspace/.qx-media/media.sqlite',"CREATE TABLE jobs(status TEXT);INSERT INTO jobs VALUES('pending');")
database('.qx-private/uploads/documents/d1/mapping.sqlite',"CREATE TABLE replacements(original TEXT,token TEXT);INSERT INTO replacements VALUES('synthetic name','[PERSON_1]');")
write('.qx-private/uploads/documents/d1/original.txt',b'synthetic name')
write('.qx-private/uploads/safe/d1.txt',b'[PERSON_1]')
write('.qx-private/uploads/documents/d1/manifest.json',json.dumps({'sha256':hashlib.sha256(b'synthetic name').hexdigest(),'mapping_file':'documents/d1/mapping.sqlite','safe_file':'safe/d1.txt'}).encode())
write('.local/dsh-home/sessions/s1.json',b'{"synthetic":true}')
write('.local/dsh-home/storages/s1.json',b'{"synthetic":true}')
write('.local/dsh-home/.credentials.yaml',b'synthetic-login-not-for-backup')
write('.local/dsh-home/profiles/profile.json',b'{"synthetic":true}')
write('.local/case-memory-runtime/instance.json',b'{"synthetic":true}')
write('.local/dsh-home/qx-wechat/qx-pending.json',b'[{"synthetic":true}]')
`,options.data],{encoding:'utf8',windowsHide:true});
  assert.equal(seed.status,0,seed.stderr);
  const saved=await createLocalBackup(options);
  assert.match(saved.snapshotId,/^[a-f0-9]{64}$/); assert.equal(saved.applicationComplete,false);
  assert.equal(saved.databaseCount,4);
  const originalBefore=fs.readdirSync(options.data,{recursive:true});
  let sourceTouched=false;
  const watch=fs.watch(options.data,{recursive:true},()=>{sourceTouched=true;});
  await assert.rejects(restoreLocalBackup({...options,destination:path.join(options.data,'must-not-stage-here')}),{code:'BACKUP_OVERLAPPING_PATHS'});
  await new Promise(resolve=>setTimeout(resolve,30));watch.close();
  assert.equal(sourceTouched,false);assert.deepEqual(fs.readdirSync(options.data,{recursive:true}),originalBefore);
  const short=spawnSync(python,['-c',`import ctypes,sys
b=ctypes.create_unicode_buffer(32768)
assert ctypes.windll.kernel32.GetShortPathNameW(sys.argv[1],b,len(b))
print(b.value)`,options.data],{encoding:'utf8',windowsHide:true});
  assert.equal(short.status,0,short.stderr);
  await assert.rejects(restoreLocalBackup({...options,destination:path.join(short.stdout.trim(),'alias-restore')}),{code:'BACKUP_OVERLAPPING_PATHS'});
  const restored=await restoreLocalBackup(options);
  assert.equal(restored.activation,'manual-review-required');
  assert.equal(fs.readFileSync(path.join(options.destination,'workspace','synthetic.txt'),'utf8'),'synthetic business data');
  assert.equal(fs.existsSync(path.join(options.destination,'.local','initialized-payload.json')),false);
  assert.equal(fs.existsSync(path.join(options.destination,'.local','dsh-home','.credentials.yaml')),false);
  const manifest=JSON.parse(fs.readFileSync(path.join(options.destination,'backup-manifest.json')));
  assert.equal(manifest.scopes.find(s=>s.path==='.local/dsh-home/.credentials.yaml').policy,'reauthorize');
  assert.equal(fs.readFileSync(path.join(options.destination,'.qx-private','uploads','safe','d1.txt'),'utf8'),'[PERSON_1]');
  const query=spawnSync(python,['-c',`import sqlite3,sys,json
from contextlib import closing
from pathlib import Path
result=[]
for name,query in [('.local/layered-knowledge.sqlite','SELECT text FROM entries'),('workspace/.qx-media/media.sqlite','SELECT status FROM jobs'),('.qx-private/uploads/documents/d1/mapping.sqlite','SELECT original,token FROM replacements')]:
 with closing(sqlite3.connect(Path(sys.argv[1])/name)) as c:result.append(c.execute(query).fetchall())
print(json.dumps(result))`,options.destination],{encoding:'utf8',windowsHide:true});
  assert.equal(query.status,0,query.stderr);
  assert.deepEqual(JSON.parse(query.stdout),[[['synthetic knowledge']],[['pending']],[['synthetic name','[PERSON_1]']]]);
  assert.equal(fs.readdirSync(options.root).some(n=>n.startsWith('.qx-')),false);
  const receiptFile=path.join(options.bundle,'completed.json'),receipt=JSON.parse(fs.readFileSync(receiptFile));
  fs.writeFileSync(receiptFile,JSON.stringify({...receipt,manifestSha256:'0'.repeat(64)}));
  await assert.rejects(restoreLocalBackup({...options,destination:path.join(options.root,'tampered')}),{code:'BACKUP_RECEIPT_MISMATCH'});
  assert.equal(fs.existsSync(path.join(options.root,'tampered')),false);
  fs.writeFileSync(receiptFile,JSON.stringify(receipt));
  const packs=fs.readdirSync(path.join(options.bundle,'repository','data'),{recursive:true,withFileTypes:true}).filter(e=>e.isFile());
  assert.ok(packs.length>0); fs.unlinkSync(path.join(packs[0].parentPath,packs[0].name));
  await assert.rejects(restoreLocalBackup({...options,destination:path.join(options.root,'missing-pack')}),{code:'BACKUP_ENGINE_FAILED'});
  assert.equal(fs.existsSync(path.join(options.root,'missing-pack')),false);
  assert.equal(fs.readdirSync(options.root).some(n=>n.startsWith('.qx-')),false);
  await assert.rejects(restoreLocalBackup(options),{code:'BACKUP_TARGET_EXISTS'});
  await assert.rejects(createLocalBackup(options),{code:'BACKUP_TARGET_EXISTS'});
  const bad={...options,destination:path.join(options.root,'wrong-password'),password:'synthetic-wrong-password'};
  await assert.rejects(restoreLocalBackup(bad),{code:'BACKUP_ENGINE_FAILED'});
  assert.equal(fs.existsSync(bad.destination),false);
  assert.equal(fs.readdirSync(options.root).some(n=>n.startsWith('.qx-')),false);
});
test('unknown paths and PostgreSQL data block backup before any repository is created',{skip:process.platform!=='win32'||!python||!restic},async t=>{
  const {createLocalBackup}=require('./local-backup.cjs');const options=fixture(t);
  fs.writeFileSync(path.join(options.data,'unknown'),'synthetic');
  await assert.rejects(createLocalBackup(options),{code:'BACKUP_SCOPE_UNSUPPORTED'});
  fs.unlinkSync(path.join(options.data,'unknown'));
  fs.mkdirSync(path.join(options.data,'.local','case-memory-runtime','database'),{recursive:true});
  await assert.rejects(createLocalBackup(options),{code:'BACKUP_POSTGRES_UNVERIFIED'});
  assert.equal(fs.existsSync(options.bundle),false);
});
test('Windows normalization aliases are rejected before creating staging',{skip:process.platform!=='win32'||!python||!restic},async t=>{
  const {createLocalBackup}=require('./local-backup.cjs');const options=fixture(t);
  for(const suffix of ['.',' '])await assert.rejects(createLocalBackup({...options,bundle:options.bundle+suffix}),{code:'BACKUP_INVALID_PATH'});
  assert.equal(fs.readdirSync(options.root).some(n=>n.startsWith('.qx-')),false);
});
test('absent drive returns an error instead of blocking the caller',{skip:process.platform!=='win32'||!python||!restic},t=>{
  const options=fixture(t),drive='ZYXWVUTSRQPONMLKJIHGFED'.split('').find(letter=>!fs.existsSync(letter+':\\'));
  assert.ok(drive,'synthetic probe needs an absent drive');
  const result=spawnSync(process.execPath,['-e',"const fs=require('node:fs');require('./desktop/local-backup.cjs').createLocalBackup(JSON.parse(fs.readFileSync(0,'utf8'))).catch(e=>console.log(e.code));"],{
    cwd:path.resolve(__dirname,'..'),input:JSON.stringify({...options,bundle:drive+':\\synthetic-never-created'}),encoding:'utf8',windowsHide:true,timeout:3000});
  assert.equal(result.status,0);assert.equal(result.stdout.trim(),'BACKUP_INVALID_PATH');
});
