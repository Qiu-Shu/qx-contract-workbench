// Offline operator entry point. No installation, background schedule, or automatic activation.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {withBackupPause,inspectScope}=require('./backup-preparation.cjs');
const historicalRoot=value=>require('./data-location.cjs').normalized(value,{allowUnavailable:true});
const ENGINE_SHA='b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830';
const WORKER=path.join(__dirname,'../bridge/backup_snapshot.py');
function fail(code){throw Object.assign(Error(code),{code});}
function local(value,allowExecutableHardlink=false){
  if(process.platform!=='win32'||typeof value!=='string'||! /^[a-z]:[\\/]/i.test(value)||value.slice(2).includes(':')||value.split(/[\\/]/).includes('..'))fail('BACKUP_INVALID_PATH');
  if(value.slice(3).split(/[\\/]/).some(p=>/[. ]$|[\x00-\x1f<>"|?*]/.test(p)||/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(p)))fail('BACKUP_INVALID_PATH');
  const result=path.resolve(value);
  for(let current=result;;current=path.dirname(current)){
    try{const s=fs.lstatSync(current);if(s.isSymbolicLink()||(!s.isDirectory()&&(!s.isFile()||(!allowExecutableHardlink&&s.nlink!==1))))fail('BACKUP_LINKED_PATH');}
    catch(error){if(error.code!=='ENOENT')throw error;}
    if(current===path.dirname(current))break;
  }
  const missing=[];let ancestor=result;
  while(!fs.existsSync(ancestor)){
    const parent=path.dirname(ancestor);if(parent===ancestor)fail('BACKUP_INVALID_PATH');
    missing.unshift(path.basename(ancestor));ancestor=parent;
  }
  return path.join(fs.realpathSync.native(ancestor),...missing);
}
function overlaps(a,b){
  a=a.toLowerCase();b=b.toLowerCase();
  return a===b||a.startsWith(b.endsWith(path.sep)?b:b+path.sep)||b.startsWith(a.endsWith(path.sep)?a:a+path.sep);
}
function disjoint(...values){for(let i=0;i<values.length;i++)for(let j=i+1;j<values.length;j++)if(overlaps(values[i],values[j]))fail('BACKUP_OVERLAPPING_PATHS');}
function absent(value){local(value);if(fs.existsSync(value))fail('BACKUP_TARGET_EXISTS');}
function childEnv(){
  return Object.fromEntries(Object.entries(process.env).filter(([k])=>['systemroot','windir','path','temp','tmp','userprofile','localappdata','appdata','pathext'].includes(k.toLowerCase())));
}
function run(exe,args,{input,cwd,env=childEnv()}={}){
  return new Promise((resolve,reject)=>{
    const child=spawn(exe,args,{cwd,env,windowsHide:true,stdio:['pipe','pipe','pipe']});
    let output='',bytes=0,limited=false;
    const timer=setTimeout(()=>{limited=true;child.kill();},600000);
    child.stdout.setEncoding('utf8');
    child.stdout.on('data',data=>{bytes+=Buffer.byteLength(data);if(bytes>16*1024*1024){limited=true;child.kill();}else output+=data;});
    child.stderr.on('data',()=>{}); // Errors can contain private paths; expose stable codes only.
    child.stdin.on('error',()=>{});
    child.on('error',()=>{clearTimeout(timer);reject(Object.assign(Error('BACKUP_PROCESS_FAILED'),{code:'BACKUP_PROCESS_FAILED'}));});
    child.on('close',code=>{clearTimeout(timer);resolve({code:limited?-1:code,output});});
    child.stdin.end(input?JSON.stringify(input):undefined);
  });
}
async function worker(python,input){
  const response=await run(python,[WORKER],{input});
  let result;try{result=JSON.parse(response.output);}catch{fail('BACKUP_WORKER_FAILED');}
  if(response.code!==0||result.error)fail(/^BACKUP_[A-Z_]+$/.test(result.error)?result.error:'BACKUP_WORKER_FAILED');
  return result;
}
function configuration(options){
  const python=local(options.python,true),restic=local(options.restic,true),bundle=local(options.bundle);
  if(!fs.statSync(python).isFile()||!fs.statSync(restic).isFile()||crypto.createHash('sha256').update(fs.readFileSync(restic)).digest('hex')!==ENGINE_SHA)fail('BACKUP_ENGINE_UNVERIFIED');
  if(typeof options.password!=='string'||options.password.length<12||options.password.length>128||/[\r\n\x00]/.test(options.password))fail('BACKUP_PASSWORD_REQUIRED');
  if(!fs.statSync(path.dirname(bundle)).isDirectory())fail('BACKUP_INVALID_PATH');
  return {python,restic,bundle};
}
async function engine(restic,repo,passwordFile,args,cwd,preflightPassword){
  const secret=passwordFile?{RESTIC_PASSWORD_FILE:passwordFile}:{RESTIC_PASSWORD:preflightPassword};
  const result=await run(restic,['--repo',repo,'--no-cache',...args],{cwd,env:{...childEnv(),...secret}});
  if(result.code!==0)fail('BACKUP_ENGINE_FAILED');
  return result.output;
}
function removeOwned(root,parent,prefix){
  // Only our successfully created random staging directory, never caller data or old backups.
  if(path.dirname(root)!==parent||!path.basename(root).startsWith(prefix))fail('BACKUP_CLEANUP_REFUSED');
  local(root);fs.rmSync(root,{recursive:true,force:true});
}
function validatePlan(plan,pgTools){
  if(plan.scopes.some(s=>s.linked||s.policy==='unclassified'))fail('BACKUP_SCOPE_UNSUPPORTED');
  if(plan.scopes.some(s=>s.path==='.local/case-memory-runtime/database')&&!pgTools)fail('BACKUP_POSTGRES_UNVERIFIED');
}
async function createLocalBackup(options){
  const {python,restic,bundle}=configuration(options),data=local(options.data);
  absent(bundle);disjoint(data,bundle);
  // Each bundle is an independent repository: failed attempts cannot advance an older backup.
  return withBackupPause(data,async source=>{
    const plan=inspectScope(source);validatePlan(plan,options.pgTools);
    const parent=path.dirname(bundle),stage=path.join(parent,'.qx-backup-'+crypto.randomUUID());
    let stageOwned=false,bundleOwned=false,complete=false;
    try{
      await worker(python,{action:'private-directory',path:stage});stageOwned=true;
      const snapshot=await worker(python,{action:'create',source,destination:path.join(stage,'snapshot'),plan,pgTools:options.pgTools});
      // Scope branches may gain new stores while the worker is running; reject changed inventories.
      if(JSON.stringify(inspectScope(source))!==JSON.stringify(plan))fail('BACKUP_SOURCE_CHANGED');
      const passwordFile=path.join(stage,'password');fs.writeFileSync(passwordFile,options.password,{flag:'wx'});
      await worker(python,{action:'private-directory',path:bundle});bundleOwned=true;
      const repo=path.join(bundle,'repository');
      await engine(restic,repo,passwordFile,['init','--repository-version','2'],stage);
      const output=await engine(restic,repo,passwordFile,['backup','snapshot','--host','ai-shixiong-offline','--tag','business-data-v1','--json'],stage);
      let summaries;
      try{summaries=output.trim().split(/\r?\n/).map(line=>JSON.parse(line)).filter(item=>item.message_type==='summary');}
      catch{fail('BACKUP_SUMMARY_INVALID');}
      const summary=summaries[0];
      if(summaries.length!==1||! /^[a-f0-9]{64}$/.test(summary.snapshot_id)||summary.total_files_processed!==snapshot.archiveFiles)fail('BACKUP_SUMMARY_INVALID');
      await engine(restic,repo,passwordFile,['check','--read-data'],stage);
      const receipt={schema:1,snapshotId:summary.snapshot_id,manifestSha256:snapshot.manifestSha256,
        fileCount:snapshot.fileCount,databaseCount:snapshot.databaseCount,postgresIncluded:snapshot.postgresIncluded,settingsCount:snapshot.settingsCount,applicationComplete:false,engineSha256:ENGINE_SHA};
      fs.writeFileSync(path.join(bundle,'completed.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
      complete=true;return receipt;
    }finally{
      if(stageOwned)removeOwned(stage,parent,'.qx-backup-');
      if(bundleOwned&&!complete){local(bundle);fs.rmSync(bundle,{recursive:true,force:true});}
    }
  });
}
async function restoreLocalBackup(options){
  const {python,restic,bundle}=configuration(options),destination=local(options.destination);
  absent(destination);disjoint(bundle,destination);
  const receiptPath=local(path.join(bundle,'completed.json'));
  if(fs.statSync(receiptPath).size>4096)fail('BACKUP_RECEIPT_INVALID');
  let receipt;try{receipt=JSON.parse(fs.readFileSync(receiptPath,'utf8'));}catch{fail('BACKUP_RECEIPT_INVALID');}
  if(receipt.schema!==1||! /^[a-f0-9]{64}$/.test(receipt.snapshotId)||! /^[a-f0-9]{64}$/.test(receipt.manifestSha256)||receipt.engineSha256!==ENGINE_SHA||receipt.applicationComplete!==false)fail('BACKUP_RECEIPT_INVALID');
  const repo=local(path.join(bundle,'repository'));
  // Inspect the authenticated manifest in memory before writing any plaintext into a destination parent.
  const manifestText=await engine(restic,repo,null,['dump',receipt.snapshotId,'/snapshot/backup-manifest.json'],undefined,options.password);
  if(crypto.createHash('sha256').update(manifestText).digest('hex')!==receipt.manifestSha256)fail('BACKUP_RECEIPT_MISMATCH');
  let manifest;try{manifest=JSON.parse(manifestText);}catch{fail('BACKUP_INVALID_MANIFEST');}
  disjoint(historicalRoot(manifest.sourceRoot),destination,bundle);
  if(manifest.postgres&&!options.pgTools)fail('BACKUP_POSTGRES_TOOLS_REQUIRED');
  const parent=path.dirname(destination),stage=path.join(parent,'.qx-restore-'+crypto.randomUUID());
  let owned=false;
  try{
    await worker(python,{action:'private-directory',path:stage});owned=true;
    const passwordFile=path.join(stage,'password');fs.writeFileSync(passwordFile,options.password,{flag:'wx'});
    const extracted=path.join(stage,'extracted');fs.mkdirSync(extracted);
    await engine(restic,repo,passwordFile,['restore',receipt.snapshotId,'--target',extracted,'--overwrite','never','--verify'],stage);
    if(JSON.stringify(fs.readdirSync(extracted))!==JSON.stringify(['snapshot']))fail('BACKUP_FILE_SET_MISMATCH');
    const restored=path.join(extracted,'snapshot');
    const checked=await worker(python,{action:'verify',root:restored,pgTools:options.pgTools});
    if(checked.manifestSha256!==receipt.manifestSha256||checked.fileCount!==receipt.fileCount||checked.databaseCount!==receipt.databaseCount||checked.postgresIncluded!==Boolean(receipt.postgresIncluded)||checked.settingsCount!==(receipt.settingsCount??0))fail('BACKUP_RECEIPT_MISMATCH');
    disjoint(historicalRoot(checked.sourceRoot),destination,bundle);
    absent(destination);
    // Re-create the published root with a protected DACL; restic's restored metadata is not trusted.
    const publish=path.join(stage,'publish');await worker(python,{action:'private-directory',path:publish});
    for(const name of fs.readdirSync(restored))fs.renameSync(path.join(restored,name),path.join(publish,name));
    await worker(python,{action:'publish',source:publish,target:destination});
    return {...receipt,activation:'manual-review-required',destination};
  }finally{if(owned)removeOwned(stage,parent,'.qx-restore-');}
}
async function reviewLocalRestore(options){
  const python=local(options.python,true),root=local(options.destination);
  if(!fs.statSync(python).isFile())fail('BACKUP_ENGINE_UNVERIFIED');
  return worker(python,{action:'review',root,pgTools:options.pgTools});
}
module.exports={createLocalBackup,restoreLocalBackup,reviewLocalRestore};
if(require.main===module){
  let input='';process.stdin.setEncoding('utf8');
  process.stdin.on('data',chunk=>{input+=chunk;if(input.length>65536)process.exit(1);});
  process.stdin.on('end',async()=>{try{
    const request=JSON.parse(input);
    const operation={backup:createLocalBackup,restore:restoreLocalBackup,review:reviewLocalRestore}[request.action];
    if(!operation)fail('BACKUP_INVALID_ACTION');
    console.log(JSON.stringify(await operation(request)));
  }catch(error){console.error(JSON.stringify({error:/^BACKUP_[A-Z_]+$/.test(error.code)?error.code:'BACKUP_FAILED'}));process.exitCode=1;}});
}
