// Prepare a new data directory. Only the desktop controller can initialize and select it.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {claimLauncher}=require('./installed-stop.cjs');
const WORKER=path.join(__dirname,'../bridge/backup_snapshot.py');
const MARKER='.local/restore-activation.json';
function fail(code){throw Object.assign(Error(code),{code});}
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
function local(value,executable=false){
  if(process.platform!=='win32'||typeof value!=='string'||! /^[a-z]:[\\/]/i.test(value)||value.slice(2).includes(':')||value.split(/[\\/]/).includes('..'))fail('BACKUP_INVALID_PATH');
  if(value.slice(3).split(/[\\/]/).some(p=>/[. ]$|[\x00-\x1f<>"|?*]/.test(p)||/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(p)))fail('BACKUP_INVALID_PATH');
  const absolute=path.resolve(value);
  for(let current=absolute;;current=path.dirname(current)){
    try{const s=fs.lstatSync(current);if(s.isSymbolicLink()||(!s.isDirectory()&&(!s.isFile()||(!executable&&s.nlink!==1))))fail('BACKUP_LINKED_PATH');}
    catch(error){if(error.code!=='ENOENT')throw error;}
    if(current===path.dirname(current))break;
  }
  const missing=[];let ancestor=absolute;
  while(!fs.existsSync(ancestor)){
    const parent=path.dirname(ancestor);if(parent===ancestor)fail('BACKUP_INVALID_PATH');
    missing.unshift(path.basename(ancestor));ancestor=parent;
  }
  return path.join(fs.realpathSync.native(ancestor),...missing);
}
function disjoint(...values){
  const roots=values.map(value=>value.toLowerCase());
  for(let i=0;i<roots.length;i++)for(let j=i+1;j<roots.length;j++){
    const a=roots[i],b=roots[j];if(a===b||a.startsWith(b.endsWith(path.sep)?b:b+path.sep)||b.startsWith(a.endsWith(path.sep)?a:a+path.sep))fail('BACKUP_OVERLAPPING_PATHS');
  }
}
function absent(value){local(value);if(fs.existsSync(value))fail('BACKUP_TARGET_EXISTS');}
function read(file,max=1024*1024){local(file);const s=fs.statSync(file);if(!s.isFile()||s.size>max)fail('BACKUP_INVALID_STATE');return fs.readFileSync(file,'utf8');}
function json(file,max){try{return JSON.parse(read(file,max));}catch(error){if(error.code?.startsWith('BACKUP_'))throw error;fail('BACKUP_INVALID_STATE');}}
function write(file,value){local(file);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});}
function worker(python,input){
  python=local(python,true);if(!fs.statSync(python).isFile())fail('BACKUP_ENGINE_UNVERIFIED');
  const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>['systemroot','windir','path','temp','tmp','userprofile','localappdata','appdata','pathext'].includes(key.toLowerCase())));
  env.PYTHONDONTWRITEBYTECODE='1';env.PYTHONIOENCODING='utf-8';env.PYTHONNOUSERSITE='1';
  return new Promise((resolve,reject)=>{
    const child=spawn(python,[WORKER],{env,windowsHide:true,stdio:['pipe','pipe','pipe']});let output='',limited=false;
    const timer=setTimeout(()=>{limited=true;child.kill();},600000);
    child.stdout.setEncoding('utf8');child.stdout.on('data',chunk=>{output+=chunk;if(Buffer.byteLength(output)>16*1024*1024){limited=true;child.kill();}});
    child.stderr.resume();child.stdin.on('error',()=>{});
    child.on('error',()=>{clearTimeout(timer);reject(Object.assign(Error('BACKUP_PROCESS_FAILED'),{code:'BACKUP_PROCESS_FAILED'}));});
    child.on('close',code=>{clearTimeout(timer);let result;try{result=JSON.parse(output);}catch{}
      if(code!==0||limited||!result||result.error){const name=/^BACKUP_[A-Z_]+$/.test(result?.error)?result.error:'BACKUP_WORKER_FAILED';reject(Object.assign(Error(name),{code:name}));}else resolve(result);
    });
    child.stdin.end(JSON.stringify(input));
  });
}
function trustedProfile(payload){
  payload=local(payload);
  const file=path.join(payload,'config/portable.json'),text=read(file,4*1024*1024);let value;
  try{value=JSON.parse(text);}catch{fail('BACKUP_PAYLOAD_INVALID');}
  if(!Array.isArray(value))fail('BACKUP_PAYLOAD_INVALID');
  return {payload,value,sha256:sha(text)};
}
function modelPreference(root){
  const file=path.join(root,'.qx-restore-review/settings/harness-profile.txt');
  if(!fs.existsSync(file))return {};
  let entries;try{entries=JSON.parse(read(file));}catch{return {};}
  if(!Array.isArray(entries))return {};
  let suggested={};
  for(const item of entries){
    if(item?.id!=='agent-default-model'||item.config?.provider!=='deepseek-official')continue;
    const config=item.config;
    if(!['deepseek-flash','deepseek-pro'].includes(config.model))continue;
    suggested={provider:'deepseek-official',model:config.model};
    if(['off','low','medium','high','max'].includes(config.reasoningEffort))suggested.reasoningEffort=config.reasoningEffort;
  }
  return suggested;
}
async function inspectDetails(options){
  const root=local(options.root),profile=trustedProfile(options.payload);
  const checked=await worker(options.python,{action:'review',root,pgTools:options.pgTools});
  const sourceRoot=require('./data-location.cjs').normalized(checked.sourceRoot,{allowUnavailable:true});
  const state=await require('./restore-pending.cjs').inspectRestoredState({root,payload:profile.payload,sourceRoot});
  const settings=checked.settings.map(item=>item.id==='harness-profile'?{...item,suggested:modelPreference(root)}:item);
  const repeated=await worker(options.python,{action:'verify',root,pgTools:options.pgTools});
  if(repeated.manifestSha256!==checked.manifestSha256||trustedProfile(profile.payload).sha256!==profile.sha256)fail('BACKUP_REVIEW_STALE');
  const reauthorization=['model-api-keys','wechat-login','content-provider-login','other-profile-secrets'];
  const result={reviewToken:sha(JSON.stringify({root,manifest:checked.manifestSha256,payload:profile.payload,profile:profile.sha256,settings,pending:state.pending})),
    counts:{files:checked.fileCount,databases:checked.databaseCount,settings:settings.length,pending:state.pending.length},settings,reauthorization,pending:state.pending,
    postgresIncluded:checked.postgresIncluded};
  return {root,sourceRoot,profile,checked,result};
}
async function inspectRestoreActivation(options){return (await inspectDetails(options)).result;}
function applyPreferences(root,destination,profile,settings,choice){
  let selected;
  if(choice===undefined||choice===false)selected=new Set();
  else if(choice===true)selected=new Set(settings.map(s=>s.id));
  else if(Array.isArray(choice)&&choice.every(id=>typeof id==='string'&&settings.some(s=>s.id===id)))selected=new Set(choice);
  else fail('BACKUP_SETTINGS_CHOICE_INVALID');
  const transform=value=>typeof value==='string'?value.replaceAll('@APP@',profile.payload.replaceAll('\\','/')).replaceAll('@DATA@',destination.replaceAll('\\','/'))
    :Array.isArray(value)?value.map(transform):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,transform(v)])):value;
  const config=transform(profile.value);
  function pause(entries){for(const item of entries){if(item?.id==='qx-personal-wechat')item.config={...item.config,autoConnect:false};if(Array.isArray(item?.insert))pause(item.insert);}}
  pause(config);
  for(const setting of settings){
    if(!selected.has(setting.id)||!Object.keys(setting.suggested).length)continue;
    if(setting.id==='desktop-locale')write(path.join(root,'.local/desktop-data/locale.json'),setting.suggested);
    if(setting.id==='wechat-preferences')write(path.join(root,'.local/dsh-home/qx-wechat/prefs.json'),setting.suggested);
    if(setting.id==='harness-profile')config.push({id:'agent-default-model',config:setting.suggested});
  }
  write(path.join(root,'.local/dsh-home/profiles/web/cordis.patch.yml'),config);
}
async function prepareRestoreActivation(options){
  const destination=local(options.destination);absent(destination);
  let lease;
  try{lease=await claimLauncher(destination);}catch(error){if(['EADDRINUSE','EACCES'].includes(error.code))fail('BACKUP_HOST_BUSY');throw error;}
  let stage,owned=false;
  try{
    const {root,sourceRoot,profile,checked,result}=await inspectDetails(options);
    if(options.reviewToken!==result.reviewToken)fail('BACKUP_REVIEW_STALE');
    disjoint(root,sourceRoot,destination,profile.payload);
    const decisions=options.decisions??{};
    if(!decisions||typeof decisions!=='object'||Array.isArray(decisions)||Object.entries(decisions).some(([id,action])=>!result.pending.some(item=>item.id===id)||!['hold','draft','cancel'].includes(action)))fail('BACKUP_PENDING_CHOICE_INVALID');
    const parent=path.dirname(destination);if(!fs.statSync(parent).isDirectory())fail('BACKUP_INVALID_PATH');
    stage=path.join(parent,'.qx-activation-'+crypto.randomUUID());
    await worker(options.python,{action:'copy-verified',root,destination:stage,manifestSha256:checked.manifestSha256,pgTools:options.pgTools});owned=true;
    const pending=await require('./restore-pending.cjs').prepareRestoredState({root:stage,payload:profile.payload,sourceRoot,destination,decisions});
    applyPreferences(stage,destination,profile,result.settings,options.applySettings);
    const id=crypto.randomUUID(),archive=path.join(stage,'.local/restore-original',id);absent(archive);
    fs.mkdirSync(path.dirname(archive),{recursive:true});fs.mkdirSync(archive);
    const receipt={schema:1,id,phase:'prepared',data:destination,sourceRestoreRoot:root,sourceRoot,sourceManifestSha256:checked.manifestSha256,
      preparedAt:new Date().toISOString(),settingsApplied:options.applySettings===true||Array.isArray(options.applySettings),
      reauthorization:result.reauthorization,postgresIncluded:checked.postgresIncluded};
    write(path.join(stage,MARKER),receipt);
    fs.renameSync(path.join(stage,'backup-manifest.json'),path.join(archive,'backup-manifest.json'));
    if(fs.existsSync(path.join(stage,'.qx-restore-review')))fs.renameSync(path.join(stage,'.qx-restore-review'),path.join(archive,'settings-review'));
    // Old completion markers are audit records; only the trusted initializer may create new ones.
    if(fs.existsSync(path.join(stage,'.local/migrations')))fs.renameSync(path.join(stage,'.local/migrations'),path.join(archive,'migrations'));
    const sealed=await worker(options.python,{action:'seal-prepared',root:stage});
    receipt.preparedManifestSha256=sealed.preparedManifestSha256;
    const receiptFile=path.join(stage,MARKER),temporary=receiptFile+'.'+crypto.randomUUID()+'.tmp';write(temporary,receipt);fs.renameSync(temporary,receiptFile);
    await worker(options.python,{action:'verify-prepared',root:stage,destination});
    if(trustedProfile(profile.payload).sha256!==profile.sha256)fail('BACKUP_REVIEW_STALE');
    absent(destination);
    await worker(options.python,{action:'publish',source:stage,target:destination});owned=false;
    return {destination,id,phase:'prepared',reauthorization:result.reauthorization,pending:pending.pending,drafts:pending.drafts??[],counts:result.counts,
      sourceManifestSha256:checked.manifestSha256,preparedManifestSha256:sealed.preparedManifestSha256,postgresIncluded:checked.postgresIncluded};
  }finally{
    try{if(owned){local(stage);if(path.dirname(stage)!==path.dirname(destination)||!path.basename(stage).startsWith('.qx-activation-'))fail('BACKUP_CLEANUP_REFUSED');fs.rmSync(stage,{recursive:true,force:true});}}
    finally{await lease.close();}
  }
}
async function verifyPreparedRestore({root,python}){
  root=local(root);const receipt=json(path.join(root,MARKER),65536);
  if(receipt.phase!=='prepared'||local(receipt.data)!==root)fail('BACKUP_PREPARED_CHANGED');
  return worker(python,{action:'verify-prepared',root});
}
module.exports={inspectRestoreActivation,prepareRestoreActivation,verifyPreparedRestore};
