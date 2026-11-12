const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createLocalBackup,restoreLocalBackup,reviewLocalRestore}=require('./local-backup.cjs');
const {initialize}=require('./installed-runtime.cjs');
const {createCaseMemoryRuntime}=require('./case-memory-runtime.cjs');
const python=process.env.QX_TEST_PYTHON,restic=process.env.QX_TEST_RESTIC;
function root(t){const result=fs.mkdtempSync(path.join(os.tmpdir(),'qx-restore-review-'));t.after(()=>fs.rmSync(result,{recursive:true,force:true}));return result;}
function put(data,name,value){const file=path.join(data,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,value);}
test('malformed or partly removed review markers still prevent initialization and memory startup',async t=>{
  const data=root(t);put(data,'backup-manifest.json','invalid synthetic manifest');
  for(const marker of ['manifest','review-directory']){
    if(marker==='review-directory'){fs.unlinkSync(path.join(data,'backup-manifest.json'));fs.mkdirSync(path.join(data,'.qx-restore-review'));}
    assert.throws(()=>initialize(data,data),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
    await assert.rejects(createCaseMemoryRuntime({data,payload:data}),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
    assert.equal(fs.existsSync(path.join(data,'.local')),false);
  }
});
test('restored settings remain inert and review exposes choices without secrets or mutations',{skip:process.platform!=='win32'||!python||!restic},async t=>{
  const temp=root(t),data=path.join(temp,'source'),destination=path.join(temp,'restored');
  put(data,'workspace/original.txt','synthetic record');
  for(const [name,value] of Object.entries({'initialized-payload.json':{schema:2,data},'runtime.json':{hostPid:null,launcherPid:123},'host-state.json':{phase:'stopped',hostPid:null,launcherPid:123}}))put(data,'.local/'+name,JSON.stringify(value));
  const settings={
    '.local/desktop-data/locale.json':'{"locale":"zh-CN","unexpected":"synthetic-private"}',
    '.local/dsh-home/profiles/web/cordis.patch.yml':'[{"id":"custom","config":{"command":"never-execute","secret":"synthetic-private","workspace":"Z:/old"}}]',
    '.local/dsh-home/qx-wechat/prefs.json':'{"format":"plain","delivery":"whole","autoReply":true,"desktopControl":true,"officeDir":"Z:/old","secret":"synthetic-private"}',
  };
  for(const [name,value] of Object.entries(settings))put(data,name,value);
  put(data,'.local/desktop-data/model-credentials/deepseek.bin','synthetic-credential-must-stay-out');
  put(data,'.local/dsh-home/qx-wechat/accounts.json','synthetic-login-must-stay-out');
  put(data,'.local/dsh-home/qx-wechat/qx-pending.json','[{"synthetic":"pending"}]');
  const options={data,destination,bundle:path.join(temp,'backup'),python,restic,password:'synthetic-restore-review-only'};
  const saved=await createLocalBackup(options);assert.equal(saved.settingsCount,3);
  const restored=await restoreLocalBackup(options);assert.equal(restored.settingsCount,3);
  const manifest=JSON.parse(fs.readFileSync(path.join(destination,'backup-manifest.json'),'utf8'));
  assert.equal(manifest.settings.length,3);
  for(const entry of manifest.settings){
    assert.equal(fs.readFileSync(path.join(destination,entry.path),'utf8'),settings[entry.sourcePath]);
    assert.equal(fs.existsSync(path.join(destination,entry.sourcePath)),false);
    assert.equal(fs.readFileSync(path.join(data,entry.sourcePath),'utf8'),settings[entry.sourcePath]);
  }
  assert.equal(fs.existsSync(path.join(destination,'.local/desktop-data/model-credentials')),false);
  assert.equal(fs.existsSync(path.join(destination,'.local/dsh-home/qx-wechat/accounts.json')),false);
  const writer=fs.openSync(path.join(destination,manifest.settings[0].path),'r+');
  try{await assert.rejects(reviewLocalRestore({destination,python}),{code:'BACKUP_SOURCE_BUSY'});}
  finally{fs.closeSync(writer);}
  const before=fs.readdirSync(destination,{recursive:true});
  const review=await reviewLocalRestore({destination,python});
  assert.equal(review.activation,'blocked');assert.equal(review.settings.length,3);
  assert.deepEqual(review.settings.find(s=>s.id==='desktop-locale').suggested,{locale:'zh-CN'});
  assert.deepEqual(review.settings.find(s=>s.id==='wechat-preferences').suggested,{format:'plain',delivery:'whole'});
  assert.ok(review.blockers.includes('pending-work-review'));
  assert.ok(review.reauthorization.includes('model-api-keys'));assert.ok(review.reauthorization.includes('wechat-login'));
  assert.doesNotMatch(JSON.stringify({saved,restored,review}),/synthetic-private|must-stay-out|never-execute|Z:\//);
  assert.deepEqual(fs.readdirSync(destination,{recursive:true}),before);
  assert.throws(()=>initialize(path.join(temp,'no-payload'),destination),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
  await assert.rejects(createCaseMemoryRuntime({data:destination,payload:temp}),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
  assert.equal(fs.existsSync(path.join(destination,'.local/case-memory-runtime/instance.json')),false);
  fs.appendFileSync(path.join(destination,manifest.settings[0].path),'tamper');
  await assert.rejects(reviewLocalRestore({destination,python}),{code:'BACKUP_FILE_HASH_MISMATCH'});
  await t.test('linked or oversized settings refuse backup instead of silently dropping configuration',async()=>{
    const file=path.join(data,'.local/desktop-data/locale.json'),link=path.join(temp,'linked-locale');
    fs.linkSync(file,link);
    try{await assert.rejects(createLocalBackup({...options,bundle:path.join(temp,'linked')}),{code:'BACKUP_SETTINGS_UNSUPPORTED'});}
    finally{fs.unlinkSync(link);}
    const bytes=fs.readFileSync(file);fs.writeFileSync(file,Buffer.alloc(1024*1024+1));
    try{await assert.rejects(createLocalBackup({...options,bundle:path.join(temp,'oversize')}),{code:'BACKUP_SETTINGS_UNSUPPORTED'});}
    finally{fs.writeFileSync(file,bytes);}
    assert.equal(fs.existsSync(path.join(temp,'linked')),false);assert.equal(fs.existsSync(path.join(temp,'oversize')),false);
  });
});
