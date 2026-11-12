// Preparation only: no archive, model call, process termination, or restore is performed here.
const fs=require('node:fs'),path=require('node:path');
const {claimLauncher}=require('./installed-stop.cjs');
function fail(code){throw Object.assign(Error(code),{code});}
function plainPath(target){
  for(let current=target;;current=path.dirname(current)){
    try{if(fs.lstatSync(current).isSymbolicLink())fail('BACKUP_LINKED_PATH');}
    catch(error){if(error.code!=='ENOENT')throw error;}
    if(current===path.dirname(current))break;
  }
}
function readRecord(data,name){
  const file=path.join(data,name);plainPath(file);
  try{
    const stat=fs.statSync(file);
    if(!stat.isFile()||stat.nlink!==1||stat.size>65536)fail('BACKUP_INVALID_STATE');
    return JSON.parse(fs.readFileSync(file,'utf8'));
  }catch(error){if(error.code==='ENOENT')return null;fail('BACKUP_INVALID_STATE');}
}
function installedData(data){
  if(typeof data!=='string'||!path.isAbsolute(data))fail('BACKUP_INVALID_ROOT');
  data=path.resolve(data);plainPath(data);
  if(!fs.statSync(data).isDirectory())fail('BACKUP_INVALID_ROOT');
  const initialized=readRecord(data,'.local/initialized-payload.json');
  if(initialized?.schema!==2||typeof initialized.data!=='string'||
    path.resolve(initialized.data).toLowerCase()!==data.toLowerCase())fail('BACKUP_UNSUPPORTED_LAYOUT');
  plainPath(path.join(data,'workspace'));
  if(!fs.statSync(path.join(data,'workspace')).isDirectory())fail('BACKUP_UNSUPPORTED_LAYOUT');
  return data;
}
function confirmStopped(data){
  const runtime=readRecord(data,'.local/runtime.json'),state=readRecord(data,'.local/host-state.json');
  if(!runtime||!state||state.phase!=='stopped'||state.hostPid!==null||runtime.hostPid!==null||
    !Number.isSafeInteger(state.launcherPid)||state.launcherPid<1||state.launcherPid!==runtime.launcherPid)fail('BACKUP_STOP_UNCONFIRMED');
  const root='.local/case-memory-runtime';
  for(const name of ['owner.json','database/postmaster.pid']){
    const file=path.join(data,root,name);plainPath(file);
    if(fs.existsSync(file))fail('BACKUP_MEMORY_NOT_STOPPED');
  }
  const memory=readRecord(data,root+'/status.json');
  if(memory&&!['stopped','not-installed'].includes(memory.phase))fail('BACKUP_MEMORY_NOT_STOPPED');
}
async function withBackupPause(data,consumer){
  if(process.platform!=='win32')fail('BACKUP_WINDOWS_REQUIRED');
  data=installedData(data);
  let lease;
  try{lease=await claimLauncher(data);}
  catch(error){if(['EADDRINUSE','EACCES'].includes(error.code))fail('BACKUP_HOST_BUSY');throw error;}
  try{
    // Same OS lease as installed-host: startup cannot initialize a new writer while held.
    confirmStopped(data);
    return await consumer(data);
  }finally{await lease.close();}
}
const policy={
  workspace:'protect','.qx-private':'protect',
  '.local/dsh-home/sessions':'protect','.local/dsh-home/storages':'protect',
  '.local/layered-knowledge.sqlite':'protect','.local/layered-knowledge.sqlite-wal':'protect','.local/layered-knowledge.sqlite-shm':'protect',
  '.local/dsh-home/.local/layered-knowledge.sqlite':'protect',
  '.local/dsh-home/.local/layered-knowledge.sqlite-wal':'protect','.local/dsh-home/.local/layered-knowledge.sqlite-shm':'protect',
  '.local/dsh-home/qx-wechat/qx-route.json':'protect','.local/dsh-home/qx-wechat/qx-seen.json':'protect',
  '.local/dsh-home/qx-wechat/qx-pending.json':'protect',
  '.local/case-memory-runtime/database':'cold-postgres','.local/case-memory-runtime/instance.json':'cold-postgres',
  '.local/case-memory-runtime/pg0':'rebuild','.local/case-memory-runtime/models':'rebuild',
  '.local/case-memory-runtime/venv':'rebuild','.local/case-memory-runtime/service.py':'rebuild',
  '.local/case-memory-runtime/requirements.in':'rebuild','.local/case-memory-runtime/requirements.lock':'rebuild',
  '.local/case-memory-runtime/dependency-plan.json':'rebuild','.local/case-memory-runtime/installed.json':'rebuild',
  '.local/case-memory-runtime/status.json':'runtime',
  '.local/desktop-data':'reauthorize','.local/dsh-home/.credentials.yaml':'reauthorize',
  '.local/dsh-home/profiles':'settings-review',
  '.local/legal-search-runtime':'rebuild','.local/agent-desktop':'rebuild',
  '.local/initialized-payload.json':'runtime','.local/runtime.json':'runtime','.local/host-state.json':'runtime',
  ...Object.fromEntries(['host','desktop'].flatMap(name=>['.log','.log.1','-events.jsonl','-events.jsonl.1'].map(suffix=>[`.local/${name}${suffix}`,'runtime']))),
};
const branches=new Set(['','.local','.local/dsh-home','.local/dsh-home/.local','.local/dsh-home/qx-wechat','.local/case-memory-runtime']);
function inspectScope(data){
  const scopes=[],files=[];
  function walk(relative,disposition,depth=0){
    if(depth>100||files.length>=200000)fail('BACKUP_INVENTORY_LIMIT');
    const absolute=path.join(data,relative),stat=fs.lstatSync(absolute);
    if(stat.isSymbolicLink()||(!stat.isDirectory()&&(!stat.isFile()||stat.nlink!==1)))fail('BACKUP_LINKED_PATH');
    if(stat.isDirectory()){
      for(const name of fs.readdirSync(absolute).sort())walk(relative+'/'+name,disposition,depth+1);
    }else files.push({path:relative,bytes:stat.size,policy:disposition,
      storage:/\.(sqlite|db)(-wal|-shm|-journal)?$/i.test(relative)?'sqlite-set':disposition==='cold-postgres'?'postgresql':'file'});
  }
  function visit(relative){
    const absolute=path.join(data,relative);plainPath(absolute);
    if(!fs.statSync(absolute).isDirectory())fail('BACKUP_UNSUPPORTED_LAYOUT');
    for(const name of fs.readdirSync(absolute).sort()){
      const next=relative?relative+'/'+name:name;
      if(branches.has(next)){visit(next);continue;}
      const disposition=policy[next]||(relative==='.local/dsh-home/qx-wechat'?'reauthorize-review':'unclassified');
      const stat=fs.lstatSync(path.join(data,next));
      const linked=stat.isSymbolicLink()||(!stat.isDirectory()&&(!stat.isFile()||stat.nlink!==1));
      scopes.push({path:next,policy:disposition,...(linked?{linked:true}:{})});
      if(['protect','cold-postgres'].includes(disposition))walk(next,disposition);
    }
  }
  visit('');
  return {schema:1,mode:'offline-preparation',backupComplete:false,
    scopeReviewRequired:scopes.some(s=>s.linked||['unclassified','settings-review','reauthorize-review','cold-postgres'].includes(s.policy)),
    scopes,files,fileCount:files.length,bytes:files.reduce((sum,f)=>sum+f.bytes,0),
    restrictions:['managed-installed-host-only','external-editors-not-locked','no-snapshot-created','credentials-need-reauthorization']};
}
async function prepareBackup(data){return withBackupPause(data,inspectScope);}
module.exports={withBackupPause,prepareBackup,inspectScope};
