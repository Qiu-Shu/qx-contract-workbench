const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const {applyUpdate,recoverUpdate,finalizeUpdate,validatePlan}=require('./incremental-install.cjs');
const vendor=path.resolve(__dirname,'../.local/install-speed-check/hdiff-proof/vendor-v5.1.3/windows64');
const hpatchz=process.env.QX_HPATCHZ_TEST_EXE||path.join(vendor,'hpatchz.exe');
const hdiffz=process.env.QX_HDIFFZ_TEST_EXE||path.join(path.dirname(hpatchz),'hdiffz.exe');
const native=fs.existsSync(hpatchz)&&fs.existsSync(hdiffz);
const digest=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function tree(root){
  const output={};const walk=dir=>{for(const item of fs.readdirSync(dir,{withFileTypes:true})){if(item.name.startsWith('.qx-update'))continue;const file=path.join(dir,item.name);if(item.isDirectory())walk(file);else{const s=fs.statSync(file);output[path.relative(root,file).split(path.sep).join('/')]={sha256:digest(file),id:s.ino,mtime:s.mtimeMs};}}};walk(root);return output;
}
function fixture(t,extra={}){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-incremental-test-'));
  t.after(()=>{assert.equal(path.dirname(root),os.tmpdir());assert.ok(path.basename(root).startsWith('qx-incremental-test-'));fs.rmSync(root,{recursive:true,force:true,maxRetries:3});});
  const app=path.join(root,'应用 中文 空格');fs.mkdirSync(path.join(app,'resources'),{recursive:true});
  const initial={'QunxingWorkbench.exe':'synthetic unchanged exe','resources/app.asar':'synthetic 0.2.6','change.txt':'old content','delete.txt':'old deletion','z-unchanged.txt':'duplicate reusable content',...extra};
  for(const [name,content] of Object.entries(initial)){fs.mkdirSync(path.dirname(path.join(app,name)),{recursive:true});fs.writeFileSync(path.join(app,name),content);}
  const target={'QunxingWorkbench.exe':'synthetic unchanged exe','resources/app.asar':'synthetic 0.2.7','change.txt':'new content','new/added.txt':'new text','a-copy.txt':'duplicate reusable content','z-unchanged.txt':'duplicate reusable content',...extra};
  const old=path.join(root,'old-changes'),next=path.join(root,'new-changes');fs.mkdirSync(old);fs.mkdirSync(next);
  const changes=[];
  for(const name of new Set([...Object.keys(initial),...Object.keys(target)])){
    if(initial[name]===target[name])continue;
    const item={path:name,oldSha256:null,newSha256:null};
    for(const [data,dir,key] of [[initial,old,'oldSha256'],[target,next,'newSha256']])if(name in data){fs.mkdirSync(path.dirname(path.join(dir,name)),{recursive:true});fs.writeFileSync(path.join(dir,name),data[name]);item[key]=digest(path.join(dir,name));}
    changes.push(item);
  }
  const patchFile=path.join(root,'changes.hdiff');
  const made=spawnSync(hdiffz,['-s-64','-c-zstd-3','-C-xxh128',old,next,patchFile],{windowsHide:true,encoding:'utf8'});
  assert.equal(made.status,0,made.stdout+made.stderr);
  const marker=changes.find(c=>c.path==='resources/app.asar');
  const plan={schema:1,product:'cn.qunxing.harness.workbench',fromVersion:'0.2.6',toVersion:'0.2.7',patchSha256:digest(patchFile),baseMarker:{path:'resources/app.asar',sha256:marker.oldSha256},targetMarker:{path:'resources/app.asar',sha256:marker.newSha256},changes};
  const planFile=path.join(root,'plan.json');const save=()=>fs.writeFileSync(planFile,JSON.stringify(plan));save();
  return {root,app,plan,save,target,before:tree(app),args:{installDir:app,planFile,patchFile,hpatchz}};
}
function assertTarget(f){const actual=tree(f.app);assert.deepEqual(Object.keys(actual).sort(),Object.keys(f.target).sort());for(const [name,content] of Object.entries(f.target))assert.equal(fs.readFileSync(path.join(f.app,name),'utf8'),content);}

test('changes-only native patch preserves unchanged file IDs and timestamps, including duplicate new content',{skip:!native},async t=>{
  const f=fixture(t);const result=await applyUpdate(f.args);assert.equal(result.status,'applied');assertTarget(f);
  const after=tree(f.app);for(const name of ['QunxingWorkbench.exe','z-unchanged.txt'])assert.deepEqual(after[name],f.before[name]);
  assert.ok(fs.existsSync(path.join(f.app,'.qx-update-transaction/backup/resources/app.asar')));
  assert.ok(!fs.existsSync(path.join(f.app,'.qx-update-transaction/backup/z-unchanged.txt')));
  assert.equal(finalizeUpdate({installDir:f.app}).status,'finalized');assert.ok(!fs.existsSync(path.join(f.app,'.qx-update-transaction')));
});
test('metadata retry is idempotent before and after finalize',{skip:!native},async t=>{
  const f=fixture(t);await applyUpdate(f.args);const before=tree(f.app);
  assert.equal((await applyUpdate(f.args)).alreadyApplied,true);assert.deepEqual(tree(f.app),before);
  finalizeUpdate({installDir:f.app});assert.equal((await applyUpdate(f.args)).alreadyApplied,true);assert.deepEqual(tree(f.app),before);
});
test('finalized cleanup errors remain successful and never roll committed files back',{skip:!native},async t=>{
  const f=fixture(t);await applyUpdate(f.args);const installed=tree(f.app),original=fs.rmSync;
  fs.rmSync=function(file,...args){if(String(file).includes('.qx-update-transaction')){const error=Error('synthetic antivirus lock');error.code='EPERM';throw error;}return original.call(fs,file,...args);};
  try{
    const finalized=finalizeUpdate({installDir:f.app});assert.equal(finalized.status,'finalized');assert.equal(finalized.cleanupPending,true);
    const recovered=recoverUpdate({installDir:f.app});assert.equal(recovered.status,'finalized');assert.equal(recovered.cleanupPending,true);
    assert.deepEqual(tree(f.app),installed);
    assert.equal((await applyUpdate(f.args)).cleanupPending,true);
  }finally{fs.rmSync=original;}
  assert.equal(finalizeUpdate({installDir:f.app}).status,'finalized');assert.deepEqual(tree(f.app),installed);
});
test('wrong baseline and bad patch leave all installed files unchanged',{skip:!native},async t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.app,'change.txt'),'locally modified');const original=tree(f.app);
  await assert.rejects(applyUpdate(f.args),{code:'UPDATE_BASE_MISMATCH'});assert.deepEqual(tree(f.app),original);
  fs.writeFileSync(path.join(f.app,'change.txt'),'old content');fs.appendFileSync(f.args.patchFile,'corruption');const baseline=tree(f.app);
  await assert.rejects(applyUpdate(f.args),{code:'UPDATE_PATCH_HASH'});assert.deepEqual(tree(f.app),baseline);assert.ok(!fs.existsSync(path.join(f.app,'.qx-update-transaction')));
});
test('failure after partial commit restores originals including file IDs',{skip:!native},async t=>{
  const f=fixture(t);
  await assert.rejects(applyUpdate({...f.args,onProgress:event=>{if(event.phase==='applying'&&event.completed===3)throw Error('synthetic interruption');}}),/synthetic interruption/);
  assert.deepEqual(tree(f.app),f.before);assert.ok(!fs.existsSync(path.join(f.app,'.qx-update-transaction')));
});
test('native malformed patch with a matching envelope hash is rejected without changing the app',{skip:!native},async t=>{
  const f=fixture(t);fs.writeFileSync(f.args.patchFile,'synthetic malformed patch');f.plan.patchSha256=digest(f.args.patchFile);f.save();
  await assert.rejects(applyUpdate(f.args),{code:'UPDATE_PATCH_FAILED'});assert.deepEqual(tree(f.app),f.before);assert.ok(!fs.existsSync(path.join(f.app,'.qx-update-transaction')));
});
test('process death after partial commit recovers and can apply again',{skip:!native},async t=>{
  const f=fixture(t);
  const script="const {applyUpdate}=require(process.argv[1]);applyUpdate({...JSON.parse(process.argv[2]),onProgress:e=>{if(e.phase==='applying'&&e.completed===3)process.exit(88);}}).catch(e=>{console.error(e);process.exit(1)});";
  const child=spawnSync(process.execPath,['-e',script,path.join(__dirname,'incremental-install.cjs'),JSON.stringify(f.args)],{windowsHide:true,encoding:'utf8'});
  assert.equal(child.status,88,child.stderr);assert.notDeepEqual(tree(f.app),f.before);
  assert.equal(recoverUpdate({installDir:f.app}).status,'recovered');assert.deepEqual(tree(f.app),f.before);
  await applyUpdate(f.args);assertTarget(f);finalizeUpdate({installDir:f.app});
});
test('apply recovers an interrupted prior transaction automatically',{skip:!native},async t=>{
  const f=fixture(t);const script="require(process.argv[1]).applyUpdate({...JSON.parse(process.argv[2]),onProgress:e=>{if(e.phase==='applying'&&e.completed===2)process.exit(89);}});";
  assert.equal(spawnSync(process.execPath,['-e',script,path.join(__dirname,'incremental-install.cjs'),JSON.stringify(f.args)],{windowsHide:true}).status,89);
  assert.equal((await applyUpdate(f.args)).status,'applied');assertTarget(f);finalizeUpdate({installDir:f.app});
});
for(const [label,code,intercept] of [
  ['before lock owner write',90,"const original=fs.writeFileSync;fs.writeFileSync=function(file,data,...rest){if(typeof file==='number'&&String(data).includes('\\\"pid\\\":'))process.exit(90);return original.call(fs,file,data,...rest);};"],
  ['after atomic lock publication',91,"const original=fs.linkSync;fs.linkSync=function(from,to,...rest){const value=original.call(fs,from,to,...rest);if(String(to).endsWith('.qx-update.lock'))process.exit(91);return value;};"],
  ['before initial journal rename',92,"const original=fs.renameSync;fs.renameSync=function(from,to,...rest){if(String(to).includes('.qx-update-init-')&&String(to).endsWith('journal.json'))process.exit(92);return original.call(fs,from,to,...rest);};"],
  ['after initialized transaction publication',93,"const original=fs.renameSync;fs.renameSync=function(from,to,...rest){const value=original.call(fs,from,to,...rest);if(String(to).endsWith('.qx-update-transaction'))process.exit(93);return value;};"],
])test('process interruption '+label+' does not block a subsequent update',{skip:!native},async t=>{
  const f=fixture(t);const script="const fs=require('node:fs');"+intercept+"require(process.argv[1]).applyUpdate(JSON.parse(process.argv[2])).catch(e=>{console.error(e);process.exit(1)});";
  const child=spawnSync(process.execPath,['-e',script,path.join(__dirname,'incremental-install.cjs'),JSON.stringify(f.args)],{windowsHide:true,encoding:'utf8'});
  assert.equal(child.status,code,child.stderr);assert.deepEqual(tree(f.app),f.before);
  assert.equal((await applyUpdate(f.args)).status,'applied');assertTarget(f);finalizeUpdate({installDir:f.app});
});
test('a retained successful transaction can be rolled back before metadata finalization',{skip:!native},async t=>{
  const f=fixture(t);await applyUpdate(f.args);assert.equal(recoverUpdate({installDir:f.app}).status,'recovered');assert.deepEqual(tree(f.app),f.before);
});
test('rollback CLI distinguishes restored files from an already committed installation',{skip:!native},async t=>{
  const f=fixture(t),script=path.join(__dirname,'incremental-install.cjs');
  const invoke=()=>spawnSync(process.execPath,[script,'rollback',f.app],{windowsHide:true,encoding:'utf8'});
  assert.equal(invoke().status,10);
  await applyUpdate(f.args);let result=invoke();assert.equal(result.status,0,result.stderr);assert.equal(JSON.parse(result.stdout).status,'recovered');assert.deepEqual(tree(f.app),f.before);
  await applyUpdate(f.args);finalizeUpdate({installDir:f.app});result=invoke();assert.equal(result.status,10);assertTarget(f);
});
test('recovery handles interruption between original-file backup and replacement',{skip:!native},async t=>{
  const f=fixture(t);await applyUpdate(f.args);
  const tx=path.join(f.app,'.qx-update-transaction'),journalFile=path.join(tx,'journal.json');
  fs.mkdirSync(path.join(tx,'patched/resources'),{recursive:true});fs.renameSync(path.join(f.app,'resources/app.asar'),path.join(tx,'patched/resources/app.asar'));
  const journal=JSON.parse(fs.readFileSync(journalFile,'utf8'));journal.phase='applying';fs.writeFileSync(journalFile,JSON.stringify(journal));
  assert.equal(recoverUpdate({installDir:f.app}).status,'recovered');assert.deepEqual(tree(f.app),f.before);
});
test('recovery waits for a recorded live patch process instead of deleting its working files',{skip:!native},async t=>{
  const f=fixture(t);await applyUpdate(f.args);
  const tx=path.join(f.app,'.qx-update-transaction'),journalFile=path.join(tx,'journal.json');
  const journal=JSON.parse(fs.readFileSync(journalFile,'utf8'));journal.phase='preparing';journal.nativePid=process.pid;fs.writeFileSync(journalFile,JSON.stringify(journal));
  const before=tree(f.app);assert.throws(()=>recoverUpdate({installDir:f.app}),{code:'UPDATE_ENGINE_RUNNING'});assert.deepEqual(tree(f.app),before);assert.ok(fs.existsSync(tx));
  journal.phase='applied';journal.nativePid=null;fs.writeFileSync(journalFile,JSON.stringify(journal));recoverUpdate({installDir:f.app});assert.deepEqual(tree(f.app),f.before);
});
test('added path collision is preserved; unrelated user-added files remain',{skip:!native},async t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.app,'a-copy.txt'),'user file');let before=tree(f.app);
  await assert.rejects(applyUpdate(f.args),{code:'UPDATE_BASE_MISMATCH'});assert.deepEqual(tree(f.app),before);
  fs.unlinkSync(path.join(f.app,'a-copy.txt'));fs.writeFileSync(path.join(f.app,'unmanaged.txt'),'user content');const sentinel=tree(f.app)['unmanaged.txt'];
  await applyUpdate(f.args);assert.deepEqual(tree(f.app)['unmanaged.txt'],sentinel);finalizeUpdate({installDir:f.app});
});
test('wrong plan paths, duplicates, reserved names and file/directory conversions are rejected',{skip:!native},t=>{
  const f=fixture(t);
  for(const name of ['../outside','resources/../outside','C:/outside','bad\\name','dir//file','NUL.txt','file:stream','trailing.','trailing ','.qx-update-transaction/work'])assert.throws(()=>validatePlan({...f.plan,changes:[...f.plan.changes,{path:name,oldSha256:null,newSha256:'1'.repeat(64)}]}));
  assert.throws(()=>validatePlan({...f.plan,changes:[...f.plan.changes,{...f.plan.changes[0],path:f.plan.changes[0].path.toUpperCase()}]}));
  assert.throws(()=>validatePlan({...f.plan,changes:[...f.plan.changes,{path:'change.txt/child',oldSha256:null,newSha256:'1'.repeat(64)}]}),/File\/directory/);
  assert.deepEqual(tree(f.app),f.before);
});
test('junction in an updated path is rejected before modifications',{skip:!native||process.platform!=='win32'},async t=>{
  const f=fixture(t);const outside=path.join(f.root,'outside');fs.mkdirSync(outside);fs.symlinkSync(outside,path.join(f.app,'new'),'junction');
  await assert.rejects(applyUpdate(f.args),{code:'UPDATE_REPARSE_POINT'});assert.deepEqual(fs.readdirSync(outside),[]);fs.unlinkSync(path.join(f.app,'new'));assert.deepEqual(tree(f.app),f.before);
});
test('unrecognized folders are not accepted as application installations',async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-incremental-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  await assert.rejects(applyUpdate({installDir:root}),{code:'UPDATE_INSTALL_DIR'});assert.deepEqual(fs.readdirSync(root),[]);
});
