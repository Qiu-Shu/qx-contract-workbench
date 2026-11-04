// The enclosing, verified installer authenticates the plan and patch. HDiffPatch
// runs only on changed-file staging; it never applies directly to the application.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');

const PRODUCT='cn.qunxing.harness.workbench';
const HPATCH_SHA256='9703c694b5955c576d9f0e26e98b60941f0bbb53b382b1f1988d75d461e580cb';
const TX='.qx-update-transaction';
const LOCK='.qx-update.lock';
const MARKER='resources/app.asar';
const HASH=/^[a-f0-9]{64}$/;

function fail(code,message){const error=new Error(message||code);error.code=code;throw error;}
function exists(file){try{fs.lstatSync(file);return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}}
function hash(file){const fd=fs.openSync(file,'r');const buffer=Buffer.allocUnsafe(1024*1024);const digest=crypto.createHash('sha256');try{let n;while((n=fs.readSync(fd,buffer,0,buffer.length,null)))digest.update(buffer.subarray(0,n));}finally{fs.closeSync(fd);}return digest.digest('hex');}
function folded(value){return process.platform==='win32'?value.toLowerCase():value;}
function relativeName(value){
  if(typeof value!=='string'||!value||value.includes('\\')||value.startsWith('/')||/[\x00-\x1f<>:"|?*]/.test(value))fail('UPDATE_PATH','Invalid package path');
  const parts=value.split('/');
  if(parts.some(p=>!p||p==='.'||p==='..'||/[. ]$/.test(p)||/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(p))||parts[0].toLowerCase().startsWith('.qx-update'))fail('UPDATE_PATH','Invalid package path');
  return value;
}
function checkedPath(root,relative){
  const file=path.resolve(root,...relativeName(relative).split('/'));
  if(path.relative(root,file).startsWith('..')||path.isAbsolute(path.relative(root,file)))fail('UPDATE_PATH');
  let cursor=root;
  for(const part of relative.split('/')){cursor=path.join(cursor,part);if(exists(cursor)&&fs.lstatSync(cursor).isSymbolicLink())fail('UPDATE_REPARSE_POINT','Reparse points are not supported in update paths');}
  return file;
}
function assertRoot(input){
  if(typeof input!=='string'||!path.isAbsolute(input))fail('UPDATE_INSTALL_DIR');
  const root=path.resolve(input);
  if(root===path.parse(root).root||!exists(root)||!fs.lstatSync(root).isDirectory()||fs.lstatSync(root).isSymbolicLink())fail('UPDATE_INSTALL_DIR');
  if(folded(fs.realpathSync.native(root))!==folded(root))fail('UPDATE_REPARSE_POINT');
  for(const name of ['QunxingWorkbench.exe',MARKER]){
    const file=checkedPath(root,name);
    if(exists(file)&&!fs.lstatSync(file).isFile())fail('UPDATE_INSTALL_DIR');
  }
  if((!exists(checkedPath(root,'QunxingWorkbench.exe'))||!exists(checkedPath(root,MARKER)))&&!exists(path.join(root,TX)))fail('UPDATE_INSTALL_DIR','Expected an existing workbench installation');
  return root;
}
function validatePlan(value){
  if(!value||value.schema!==1||value.product!==PRODUCT||!/^\d+\.\d+\.\d+$/.test(value.fromVersion)||!/^\d+\.\d+\.\d+$/.test(value.toVersion)||value.fromVersion===value.toVersion||!HASH.test(value.patchSha256)||!Array.isArray(value.changes)||!value.changes.length)fail('UPDATE_PLAN');
  for(const marker of [value.baseMarker,value.targetMarker])if(!marker||marker.path!==MARKER||!HASH.test(marker.sha256))fail('UPDATE_PLAN');
  const names=new Set();
  const changes=value.changes.map(item=>{
    if(!item||typeof item!=='object')fail('UPDATE_PLAN');
    const name=relativeName(item.path),key=name.toLowerCase();
    if(names.has(key)||(item.oldSha256!==null&&!HASH.test(item.oldSha256))||(item.newSha256!==null&&!HASH.test(item.newSha256))||item.oldSha256===item.newSha256)fail('UPDATE_PLAN');
    names.add(key);return {path:name,oldSha256:item.oldSha256,newSha256:item.newSha256};
  }).sort((a,b)=>(a.path===MARKER?1:0)-(b.path===MARKER?1:0)||a.path.localeCompare(b.path,'en'));
  for(const item of changes){let parent=path.posix.dirname(item.path);while(parent!=='.'){if(names.has(parent.toLowerCase()))fail('UPDATE_PLAN','File/directory type changes require a full repair installer');parent=path.posix.dirname(parent);}}
  const marker=changes.find(c=>c.path===MARKER);
  if(!marker||marker.oldSha256!==value.baseMarker.sha256||marker.newSha256!==value.targetMarker.sha256)fail('UPDATE_PLAN');
  return {schema:1,product:PRODUCT,fromVersion:value.fromVersion,toVersion:value.toVersion,patchSha256:value.patchSha256,baseMarker:{path:MARKER,sha256:value.baseMarker.sha256},targetMarker:{path:MARKER,sha256:value.targetMarker.sha256},changes};
}
function planId(plan){return crypto.createHash('sha256').update(JSON.stringify(plan)).digest('hex');}
function syncFile(file){const fd=fs.openSync(file,'r+');try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}}
function writeJournal(tx,journal){
  const temporary=path.join(tx,'.journal-'+crypto.randomUUID()+'.tmp');
  const fd=fs.openSync(temporary,'wx');try{fs.writeFileSync(fd,JSON.stringify(journal));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
  fs.renameSync(temporary,path.join(tx,'journal.json'));
}
function initializeTransaction(root,journal){
  const staging=path.join(root,`.qx-update-init-${process.pid}-${crypto.randomUUID()}`);
  fs.mkdirSync(staging);
  try{writeJournal(staging,journal);fs.renameSync(staging,path.join(root,TX));}
  catch(error){
    // The fixed transaction path is published only after its journal is durable.
    if(exists(staging)){if(path.dirname(staging)!==root||!path.basename(staging).startsWith('.qx-update-init-'))fail('UPDATE_PATH');safeTree(staging);fs.rmSync(staging,{recursive:true,force:true});}
    throw error;
  }
}
function readJournal(root){
  const tx=path.join(root,TX);
  if(!exists(tx))return null;
  if(fs.lstatSync(tx).isSymbolicLink()||!fs.lstatSync(tx).isDirectory())fail('UPDATE_REPARSE_POINT');
  const file=path.join(tx,'journal.json');
  if(!exists(file)){if(fs.readdirSync(tx).length)fail('UPDATE_JOURNAL','Unrecognized update transaction');fs.rmdirSync(tx);return null;}
  if(fs.lstatSync(file).isSymbolicLink())fail('UPDATE_REPARSE_POINT');
  let journal;try{journal=JSON.parse(fs.readFileSync(file,'utf8'));}catch{fail('UPDATE_JOURNAL');}
  const plan=validatePlan(journal.plan);
  if(journal.schema!==1||folded(journal.installDir)!==folded(root)||journal.planId!==planId(plan)||!['preparing','applying','applied','rolled-back','finalized'].includes(journal.phase)||!Array.isArray(journal.createdDirectories))fail('UPDATE_JOURNAL');
  if(journal.nativePid!=null&&(!Number.isSafeInteger(journal.nativePid)||journal.nativePid<1))fail('UPDATE_JOURNAL');
  journal.plan=plan;
  const parents=new Set();for(const item of plan.changes){let name=path.posix.dirname(item.path);while(name!=='.'){parents.add(name);name=path.posix.dirname(name);}}
  for(const name of journal.createdDirectories){if(!parents.has(name))fail('UPDATE_JOURNAL');checkedPath(root,name);}
  return journal;
}
function safeTree(root){
  if(!exists(root))return;
  if(fs.lstatSync(root).isSymbolicLink())fail('UPDATE_REPARSE_POINT');
  if(fs.lstatSync(root).isDirectory())for(const item of fs.readdirSync(root))safeTree(path.join(root,item));
}
function cleanup(root){
  const tx=path.join(root,TX);
  if(path.dirname(tx)!==root||path.basename(tx)!==TX)fail('UPDATE_PATH');
  safeTree(tx);
  for(const name of fs.readdirSync(tx)){
    if(name==='journal.json')continue;
    if(name!=='work'&&name!=='patched'&&name!=='backup'&&!/^\.journal-[0-9a-f-]+\.tmp$/.test(name))fail('UPDATE_JOURNAL','Unrecognized transaction entry');
    fs.rmSync(path.join(tx,name),{recursive:true,force:true});
  }
  fs.unlinkSync(path.join(tx,'journal.json'));fs.rmdirSync(tx);
}
function fileMatches(root,name,digest){
  const file=checkedPath(root,name);
  return digest===null?!exists(file):exists(file)&&fs.lstatSync(file).isFile()&&hash(file)===digest;
}
function verifyFiles(root,plan,which){
  for(const item of plan.changes)if(!fileMatches(root,item.path,item[which]))fail(which==='oldSha256'?'UPDATE_BASE_MISMATCH':'UPDATE_TARGET_MISMATCH',`Unexpected file: ${item.path}`);
}
function createdDirectories(root,changes){
  const result=new Set();
  for(const item of changes){if(item.newSha256===null)continue;let parent=path.posix.dirname(item.path);while(parent!=='.'){const dir=checkedPath(root,parent);if(!exists(dir))result.add(parent);else if(!fs.lstatSync(dir).isDirectory())fail('UPDATE_PATH');parent=path.posix.dirname(parent);}}
  return [...result].sort((a,b)=>b.split('/').length-a.split('/').length);
}
function recoverUnlocked(root,journal){
  if(!journal)return {status:'no-transaction'};
  const tx=path.join(root,TX);
  if(journal.phase==='preparing'&&journal.nativePid&&processAlive(journal.nativePid))fail('UPDATE_ENGINE_RUNNING','Previous patch preparation is still running; retry after it exits');
  if(journal.phase==='finalized')return cleanupFinalized(root,journal);
  if(journal.phase==='rolled-back'||journal.phase==='preparing'){cleanup(root);return {status:'recovered'};}
  const backup=path.join(tx,'backup');safeTree(backup);
  for(const item of [...journal.plan.changes].reverse()){
    const current=checkedPath(root,item.path),saved=checkedPath(backup,item.path);
    if(item.oldSha256!==null&&exists(saved)){
      if(!fileMatches(backup,item.path,item.oldSha256))fail('UPDATE_ROLLBACK_INCOMPLETE','Backup checksum differs');
      if(exists(current)){
        if(fileMatches(root,item.path,item.oldSha256)){fs.unlinkSync(saved);continue;}
        if(item.newSha256===null||!fileMatches(root,item.path,item.newSha256))fail('UPDATE_ROLLBACK_INCOMPLETE','A file changed outside the updater');
        fs.unlinkSync(current);
      }
      fs.mkdirSync(path.dirname(current),{recursive:true});fs.renameSync(saved,current);
    }else if(item.oldSha256!==null){
      if(!fileMatches(root,item.path,item.oldSha256))fail('UPDATE_ROLLBACK_INCOMPLETE','Original file or backup is missing');
    }else if(exists(current)){
      if(!fileMatches(root,item.path,item.newSha256))fail('UPDATE_ROLLBACK_INCOMPLETE','An added file changed outside the updater');
      fs.unlinkSync(current);
    }
  }
  for(const name of journal.createdDirectories){try{fs.rmdirSync(checkedPath(root,name));}catch(e){if(!['ENOENT','ENOTEMPTY','EEXIST'].includes(e.code))throw e;}}
  journal.phase='rolled-back';writeJournal(tx,journal);cleanup(root);
  return {status:'recovered',version:journal.plan.fromVersion};
}
function processAlive(pid){try{process.kill(pid,0);return true;}catch(error){return error.code!=='ESRCH';}}
function acquire(root){
  const file=path.join(root,LOCK);
  const temporary=path.join(root,`.qx-update-owner-${process.pid}-${crypto.randomUUID()}.tmp`);
  const fd=fs.openSync(temporary,'wx');
  try{fs.writeFileSync(fd,JSON.stringify({schema:1,pid:process.pid}));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
  const identity=fs.statSync(temporary).ino;
  try{
    for(let attempt=0;attempt<2;attempt++){
      try{
        // A hard link publishes a complete owner record without an empty-lock window.
        fs.linkSync(temporary,file);
        return ()=>{if(exists(file)&&fs.lstatSync(file).ino===identity)fs.unlinkSync(file);};
      }catch(e){if(e.code!=='EEXIST')throw e;}
      const previous=fs.lstatSync(file);if(previous.isSymbolicLink())fail('UPDATE_REPARSE_POINT');
      let owner;try{owner=JSON.parse(fs.readFileSync(file,'utf8'));}catch{fail('UPDATE_BUSY');}
      if(owner.schema!==1||!Number.isSafeInteger(owner.pid)||owner.pid<1)fail('UPDATE_BUSY');
      if(processAlive(owner.pid))fail('UPDATE_BUSY','Another update is running');
      if(!exists(file)||fs.lstatSync(file).ino!==previous.ino)continue;
      fs.unlinkSync(file);
    }
    fail('UPDATE_BUSY');
  }finally{
    try{fs.unlinkSync(temporary);}catch(error){if(!['ENOENT','EPERM','EACCES'].includes(error.code))throw error;}
  }
}
async function nativePatch(executable,work,patched,patch,onSpawn){
  await new Promise((resolve,reject)=>{
    const child=spawn(executable,['-C-all',work,patch,patched],{windowsHide:true,stdio:['ignore','pipe','pipe']});
    let preparationError;
    for(const stream of [child.stdout,child.stderr])stream.resume();
    child.on('spawn',()=>{try{onSpawn(child.pid);}catch(error){preparationError=error;child.kill();}});
    child.on('error',reject);child.on('exit',code=>{if(preparationError)reject(preparationError);else if(code===0)resolve();else{const error=new Error(`HDiffPatch exited ${code}`);error.code='UPDATE_PATCH_FAILED';error.nativeExitCode=code;reject(error);}});
  });
}
function verifyWork(work,plan){
  const expected=new Set(plan.changes.filter(c=>c.newSha256!==null).map(c=>c.path));
  safeTree(work);const files=[];
  const visit=dir=>{for(const item of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,item.name);if(item.isDirectory())visit(file);else files.push(path.relative(work,file).split(path.sep).join('/'));}};
  visit(work);
  if(files.length!==expected.size||files.some(name=>!expected.has(name)))fail('UPDATE_PATCH_CONTENTS');
  for(const item of plan.changes)if(item.newSha256!==null){if(!fileMatches(work,item.path,item.newSha256))fail('UPDATE_TARGET_MISMATCH');syncFile(checkedPath(work,item.path));}
}
async function applyUpdate({installDir,planFile,patchFile,hpatchz,onProgress=()=>{}}){
  const root=assertRoot(installDir),release=acquire(root);
  try{
    const plan=validatePlan(JSON.parse(fs.readFileSync(planFile,'utf8'))),id=planId(plan);
    let previous=readJournal(root);
    if(previous?.phase==='applied'){
      if(previous.planId!==id)fail('UPDATE_PENDING_FINALIZE');
      verifyFiles(root,plan,'newSha256');return {status:'applied',version:plan.toVersion,alreadyApplied:true,changedFiles:plan.changes.length};
    }
    if(previous){const recovered=recoverUnlocked(root,previous);if(recovered.cleanupPending){if(previous.planId===id){verifyFiles(root,plan,'newSha256');return {status:'applied',version:plan.toVersion,alreadyApplied:true,changedFiles:plan.changes.length,cleanupPending:true};}fail('UPDATE_CLEANUP_PENDING');}}
    if(fileMatches(root,MARKER,plan.targetMarker.sha256)){verifyFiles(root,plan,'newSha256');return {status:'applied',version:plan.toVersion,alreadyApplied:true,changedFiles:plan.changes.length};}
    if(hash(patchFile)!==plan.patchSha256)fail('UPDATE_PATCH_HASH');
    if(hash(hpatchz)!==HPATCH_SHA256)fail('UPDATE_PATCH_ENGINE');
    if(!fileMatches(root,MARKER,plan.baseMarker.sha256))fail('UPDATE_BASE_MISMATCH');
    verifyFiles(root,plan,'oldSha256');
    const tx=path.join(root,TX);
    const journal={schema:1,installDir:root,plan,planId:id,phase:'preparing',createdDirectories:createdDirectories(root,plan.changes)};
    initializeTransaction(root,journal);
    try{
      const work=path.join(tx,'work'),patched=path.join(tx,'patched'),backup=path.join(tx,'backup');fs.mkdirSync(work);fs.mkdirSync(backup);
      onProgress({phase:'preparing',changedFiles:plan.changes.length});
      for(const item of plan.changes)if(item.oldSha256!==null){const target=checkedPath(work,item.path);fs.mkdirSync(path.dirname(target),{recursive:true});fs.copyFileSync(checkedPath(root,item.path),target);}
      await nativePatch(path.resolve(hpatchz),work,patched,path.resolve(patchFile),pid=>{journal.nativePid=pid;writeJournal(tx,journal);});
      journal.nativePid=null;writeJournal(tx,journal);verifyWork(patched,plan);
      verifyFiles(root,plan,'oldSha256');journal.phase='applying';writeJournal(tx,journal);
      let completed=0;
      for(const item of plan.changes){
        const target=checkedPath(root,item.path),saved=checkedPath(backup,item.path);
        if(item.oldSha256!==null){fs.mkdirSync(path.dirname(saved),{recursive:true});fs.renameSync(target,saved);}
        if(item.newSha256!==null){fs.mkdirSync(path.dirname(target),{recursive:true});fs.renameSync(checkedPath(patched,item.path),target);}
        onProgress({phase:'applying',completed:++completed,total:plan.changes.length,path:item.path});
      }
      verifyFiles(root,plan,'newSha256');journal.phase='applied';writeJournal(tx,journal);
      return {status:'applied',version:plan.toVersion,alreadyApplied:false,changedFiles:plan.changes.length};
    }catch(error){
      try{recoverUnlocked(root,readJournal(root));}catch(recoveryError){error.code='UPDATE_ROLLBACK_INCOMPLETE';error.recoveryError=recoveryError.message;}
      throw error;
    }
  }finally{release();}
}
function recoverUpdate({installDir}){const root=assertRoot(installDir),release=acquire(root);try{return recoverUnlocked(root,readJournal(root));}finally{release();}}
function cleanupFinalized(root,journal){
  try{cleanup(root);return {status:'finalized',version:journal.plan.toVersion};}
  catch(error){return {status:'finalized',version:journal.plan.toVersion,cleanupPending:true,cleanupError:error.code||'UPDATE_CLEANUP_FAILED'};}
}
function finalizeUpdate({installDir}){
  const root=assertRoot(installDir),release=acquire(root);
  try{
    const journal=readJournal(root);if(!journal)return {status:'no-transaction'};
    if(journal.phase!=='applied'&&journal.phase!=='finalized')fail('UPDATE_NOT_APPLIED');
    verifyFiles(root,journal.plan,'newSha256');journal.phase='finalized';writeJournal(path.join(root,TX),journal);
    return cleanupFinalized(root,journal);
  }finally{release();}
}
module.exports={applyUpdate,recoverUpdate,finalizeUpdate,validatePlan,HPATCH_SHA256};
if(require.main===module){
  const [command,installDir,planFile,patchFile,hpatchz]=process.argv.slice(2);
  const run=command==='apply'?()=>applyUpdate({installDir,planFile,patchFile,hpatchz}):['recover','rollback'].includes(command)?()=>recoverUpdate({installDir}):command==='finalize'?()=>finalizeUpdate({installDir}):()=>fail('UPDATE_ARGUMENTS');
  Promise.resolve().then(run).then(result=>{console.log(JSON.stringify(result));if(command==='rollback'&&result.status!=='recovered')process.exitCode=10;}).catch(error=>{console.error(JSON.stringify({status:'failed',code:error.code||'UPDATE_FAILED',message:error.message,...(error.recoveryError?{recoveryError:error.recoveryError}:{})}));process.exitCode=1;});
}
