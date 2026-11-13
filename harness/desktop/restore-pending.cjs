// Offline restore preparation. Only the caller's unpublished copy may be changed.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url');
const WECHAT='.local/dsh-home/qx-wechat/qx-pending.json',CONTENT='.local/content-watch/state.json';
const SCHEDULE='.local/dsh-home/storages/schedule.json',WORKSPACE='.local/dsh-home/storages/workspace.json';
const SESSIONS='.local/dsh-home/sessions',PENDING='.local/restore-pending.json',ORIGINAL='.local/restore-original';
function fail(code){throw Object.assign(Error(code),{code});}
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
function plain(file){
 for(let current=path.resolve(file);;current=path.dirname(current)){
  try{const stat=fs.lstatSync(current);if(stat.isSymbolicLink()||(stat.isFile()&&stat.nlink!==1))fail('RESTORE_PENDING_LINK');}
  catch(error){if(error.code!=='ENOENT')throw error;}
  if(current===path.dirname(current))break;
 }
}
function absolute(value){if(typeof value!=='string'||!path.isAbsolute(value))fail('RESTORE_PENDING_PATH');plain(value);return path.resolve(value);}
function record(root,relative){
 const file=path.join(root,relative);plain(file);
 try{if(!fs.statSync(file).isFile())fail('RESTORE_PENDING_FORMAT');const value=JSON.parse(fs.readFileSync(file,'utf8'));if(!object(value))fail('RESTORE_PENDING_FORMAT');return value;}
 catch(error){if(error.code==='ENOENT')return null;if(error.code?.startsWith('RESTORE_'))throw error;fail('RESTORE_PENDING_FORMAT');}
}
function write(root,relative,value){const file=path.join(root,relative);plain(file);fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});const temp=file+'.'+crypto.randomUUID()+'.tmp';fs.writeFileSync(temp,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});fs.renameSync(temp,file);}
function relativeInside(root,value){const rel=path.relative(root,value);return rel===''||(!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel));}
function sourceRelative(value,sourceRoot,scope='workspace'){
 if(typeof value!=='string')return null;
 const api=path.win32.isAbsolute(sourceRoot)&&/^[A-Za-z]:[\\/]|^\\\\/.test(sourceRoot)?path.win32:path.posix;
 const base=api.resolve(sourceRoot,scope),resolved=api.resolve(value),relative=api.relative(base,resolved);
 if(!api.isAbsolute(value)||relative==='..'||relative.startsWith('..'+api.sep)||api.isAbsolute(relative))return null;
 return relative.split(api.sep).filter(Boolean);
}
function rebind(value,sourceRoot,destination,scope='workspace'){
 const relative=sourceRelative(value,sourceRoot,scope);return relative===null?value:path.join(destination,scope,...relative);
}
function redact(value){return String(value??'').replace(/\b(?:Bearer\s+|sk-)[A-Za-z0-9_.\-]+/gi,'[凭据已隐藏]').replace(/((?:api[_ -]?key|token|password|secret|authorization|cookie)\s*[:=]\s*)[^\s,;]+/gi,'$1[凭据已隐藏]');}
function taskText(value){
 if(!object(value))return '';
 const chunks=[];
 for(const key of ['title','instruction','prompt','text','content','phase'])if(typeof value[key]==='string')chunks.push(value[key]);
 for(const key of ['items','content'])if(Array.isArray(value[key]))for(const item of value[key])chunks.push(taskText(item));
 return redact(chunks.filter(Boolean).join('\n'));
}
function entry(kind,key,label,status,body){return {id:kind+':'+crypto.createHash('sha256').update(key).digest('hex').slice(0,24),kind,label,preview:taskText(body).slice(0,500),status};}
async function loadHarness(payload){
 try{
  payload=absolute(payload);const req=createRequire(path.join(payload,'package.json'));
  const load=name=>import(pathToFileURL(req.resolve('@deepseek-ai/'+name)).href);
  for(const name of ['dsh-session','dsh-session-persistence-jsonl','dsh-session-format-catalog']){
   const pkg=JSON.parse(fs.readFileSync(req.resolve('@deepseek-ai/'+name+'/package.json'),'utf8'));if(pkg.version!=='0.2.2-alpha.2')fail('RESTORE_PENDING_HARNESS_VERSION');
  }
  return {load,...await load('cordis'),...await load('dsh-session'),persistence:await load('dsh-session-persistence-jsonl'),...await load('dsh-session-format-catalog'),...await load('dsh-session-format-catalog/message-projections')};
 }catch(error){if(error.code?.startsWith('RESTORE_'))throw error;fail('RESTORE_PENDING_HARNESS_UNAVAILABLE');}
}
async function withPersistence(lib,root,compression,run){
 const ctx=new lib.Context(),fiber=ctx.plugin(lib.persistence,{root,compression});
 try{await fiber.await();return await run(ctx.sessionPersistence);}
 finally{await fiber.dispose();}
}
function sessionFiles(root){
 const files=[];
 function visit(dir,depth){plain(dir);if(depth>3)fail('RESTORE_PENDING_SESSION_FORMAT');
  for(const item of fs.readdirSync(dir,{withFileTypes:true})){
   const file=path.join(dir,item.name);plain(file);
   if(item.isDirectory())visit(file,depth+1);
   else if(depth===2&&item.isFile()&&/^session(?:\.v[1-9][0-9]*)?\.jsonl(?:\.zstd)?$/.test(item.name))files.push(file);
   else if(!(depth===2&&item.isFile()&&item.name==='session.lock'))fail('RESTORE_PENDING_SESSION_FORMAT');
  }
 }
 if(fs.existsSync(root))visit(root,0);return files;
}
function foldInbox(events){
 const state={'next-turn':[],'next-step':[]};
 for(const event of events){
  if(event.type!=='agent/inbox/spliced')continue;
  const d=event.data,list=state[d.target],removed=d.removedCount??0;
  if(!list||!Number.isSafeInteger(d.start)||d.start<0||d.start>list.length||!Number.isSafeInteger(removed)||removed<0||d.start+removed>list.length||!Array.isArray(d.inserted))fail('RESTORE_PENDING_INBOX_FORMAT');
  list.splice(d.start,removed,...d.inserted);const ids=new Set();
  for(const message of [...state['next-turn'],...state['next-step']]){if(!object(message)||typeof message.id!=='string'||ids.has(message.id))fail('RESTORE_PENDING_INBOX_FORMAT');ids.add(message.id);}
 }
 return state;
}
async function inspectAll({root,payload,sourceRoot}){
 root=absolute(root);sourceRoot=absolute(sourceRoot);if(!fs.statSync(root).isDirectory())fail('RESTORE_PENDING_PATH');
 const pending=[],details=new Map(),records=new Map(),sessions=[],externalWorkspaces=new Set(),externalSessions=new Set(),externalLocations=new Set();
 const add=(kind,key,label,status,body)=>{const p=entry(kind,key,label,status,body);if(details.has(p.id))fail('RESTORE_PENDING_DUPLICATE');pending.push(p);details.set(p.id,body);};
 const external=(cwd)=>{const key=cwd??'(no-cwd)';if(externalLocations.has(key))return;externalLocations.add(key);add('external-workspace',key,'外部工作位置需重新选择','quarantined',{text:'原工作位置未自动绑定：'+(cwd??'未记录工作位置')+'。相关会话只保留在恢复审计中，需重新选择工作位置后再处理。'});};
 const wx=record(root,WECHAT);if(wx){
  if(wx.version!==1||!Array.isArray(wx.pending)||!Array.isArray(wx.failed)||!Array.isArray(wx.history)||!(wx.active===null||object(wx.active)))fail('RESTORE_PENDING_FORMAT');
  records.set(WECHAT,wx);
  for(const [status,list] of [['pending',wx.pending],['active',wx.active?[wx.active]:[]],['failed',wx.failed]])for(const [index,item] of list.entries()){
   if(!object(item)||typeof item.id!=='string'||!Array.isArray(item.items))fail('RESTORE_PENDING_FORMAT');
   add('wechat',status+':'+item.id+':'+index,'微信待办',status,item);
  }
 }
 const cw=record(root,CONTENT);if(cw){
  if(cw.version!==1||typeof cw.enabled!=='boolean'||!(cw.active==null||object(cw.active))||!(cw.lastReport==null||object(cw.lastReport)))fail('RESTORE_PENDING_FORMAT');
  records.set(CONTENT,cw);
  if(cw.enabled)add('content-watch','automatic','拓客内容定时整理','scheduled',{text:'恢复后保持暂停，需在工作台重新启用。'});
  if(cw.active)add('content-watch','active:'+String(cw.active.id),'拓客内容中断任务',cw.active.phase||'active',{...cw.active,text:cw.lastReport?.content||''});
  if(cw.lastReport?.pending&&!cw.active)add('content-watch','report:'+String(cw.lastReport.id),'拓客内容待核查报告',cw.lastReport.submitted===false?'not-submitted':'submission-uncertain',cw.lastReport);
 }
 const schedules=record(root,SCHEDULE);if(schedules){
  if(schedules.unit?.name!=='schedule'||schedules.unit.version!==1||!(schedules.global===null||object(schedules.global))||!object(schedules.tables?.tasks)||Object.keys(schedules.tables).some(k=>k!=='tasks'))fail('RESTORE_PENDING_FORMAT');
  records.set(SCHEDULE,schedules);
  for(const [id,task] of Object.entries(schedules.tables.tasks)){
   if(!object(task)||!object(task.record)||task.record.id!==id||typeof task.sessionId!=='string'||!['active','inactive',undefined].includes(task.status))fail('RESTORE_PENDING_FORMAT');
   if(task.status!=='inactive')add('schedule',id,'会话定时提醒','active',task.record);
  }
 }
 const workspace=record(root,WORKSPACE);if(workspace){
  if(workspace.unit?.name!=='workspace'||workspace.unit.version!==2||!object(workspace.global)||!Array.isArray(workspace.global.workspaceIds)||!object(workspace.tables?.workspaces)||Object.values(workspace.tables.workspaces).some(row=>!object(row)||typeof row.path!=='string'||!Array.isArray(row.sessionIds)))fail('RESTORE_PENDING_FORMAT');
  records.set(WORKSPACE,workspace);
  for(const [id,row] of Object.entries(workspace.tables.workspaces))if(sourceRelative(row.path,sourceRoot)===null){externalWorkspaces.add(id);external(row.path);}
 }
 const files=sessionFiles(path.join(root,SESSIONS));let lib,compression;
 if(files.length){
  compression=files[0].endsWith('.zstd')?'zstd':'none';if(files.some(file=>file.endsWith('.zstd')!==(compression==='zstd')))fail('RESTORE_PENDING_SESSION_FORMAT');
  lib=await loadHarness(payload);
  await withPersistence(lib,path.join(root,SESSIONS),compression,async store=>{
   const listing=await store.list();const directories=new Set(files.map(file=>path.dirname(file)));
   if(listing.length!==directories.size)fail('RESTORE_PENDING_SESSION_FORMAT');
   for(const snapshot of listing){const handle=await store.open(snapshot.header.id,'read');try{
    const {events,eventState}=await handle.read();const inbox=foldInbox(events);
    sessions.push({header:handle.header,inheritedEventCount:handle.inheritedEventCount,events,eventState,inbox});
    if(sourceRelative(handle.header.cwd,sourceRoot)===null){externalSessions.add(handle.header.id);external(handle.header.cwd);}
    for(const target of ['next-turn','next-step'])for(const message of inbox[target])add('session-inbox',handle.header.id+':'+target+':'+message.id,'会话待处理消息',target,message);
   }finally{await handle.close();}}
  });
 }
 for(const relative of ['.local/dsh-home/qx-wechat/qx-route.json','.local/content-watch/session.json']){
  const binding=record(root,relative);if(binding&&externalSessions.has(binding.sessionId))records.set(relative,binding);
 }
 const previous=record(root,PENDING);
 if(previous){
  if(previous.schema!==1||!Array.isArray(previous.pending)||!(previous.history===undefined||Array.isArray(previous.history)))fail('RESTORE_PENDING_FORMAT');
  for(const item of previous.pending){
   if(!object(item)||!/^[-a-z]+:[a-f0-9]{24}$/.test(item.id)||typeof item.kind!=='string'||typeof item.label!=='string'||typeof item.preview!=='string'||!['hold','draft','cancel'].includes(item.decision))fail('RESTORE_PENDING_FORMAT');
   if(item.decision==='hold'&&!details.has(item.id)){pending.push({id:item.id,kind:item.kind,label:item.label,preview:redact(item.preview).slice(0,500),status:item.status});details.set(item.id,{text:item.text??item.preview});}
  }
 }
 return {root,sourceRoot,pending,details,records,sessions,lib,compression,previous,externalWorkspaces,externalSessions};
}
function publicResult(state){return {pending:state.pending,counts:{total:state.pending.length,sessions:state.sessions.length}};}
async function inspectRestoredState(options){return publicResult(await inspectAll(options));}
function preserve(root,relative,move=false){
 const from=path.join(root,relative);let saved=path.join(ORIGINAL,relative);if(fs.existsSync(path.join(root,saved)))saved=path.join(ORIGINAL,crypto.randomUUID(),relative);
 const to=path.join(root,saved);plain(to);if(!relativeInside(root,from)||!relativeInside(root,to))fail('RESTORE_PENDING_PATH');fs.mkdirSync(path.dirname(to),{recursive:true,mode:0o700});
 if(move)fs.renameSync(from,to);else fs.cpSync(from,to,{recursive:true,errorOnExist:true,force:false});return saved.replaceAll('\\','/');
}
async function prepareRestoredState(options){
 const root=absolute(options.root),sourceRoot=absolute(options.sourceRoot),destination=absolute(options.destination);
 if(relativeInside(sourceRoot,root)||relativeInside(root,sourceRoot)||relativeInside(sourceRoot,destination)||relativeInside(destination,sourceRoot))fail('RESTORE_PENDING_SOURCE');
 const state=await inspectAll(options),decisions=options.decisions??{};
 if(!object(decisions)||Object.entries(decisions).some(([id,action])=>!state.details.has(id)||!['hold','draft','cancel'].includes(action)))fail('RESTORE_PENDING_DECISION');
 const originals=[],drafts=[];
 if(state.previous)originals.push(preserve(root,PENDING));
 for(const [relative,value] of state.records){
  originals.push(preserve(root,relative));
  if(relative===WECHAT){value.pending=[];value.active=null;}
  if(relative===CONTENT){value.enabled=false;value.active=null;value.status='paused';value.message='恢复待办已单独保留，自动整理暂停。';if(value.lastReport?.pending)value.lastReport.pending=false;value.lastReport&&(value.lastReport.path=rebind(value.lastReport.path,sourceRoot,destination,'.local/content-watch/reports'));}
  if(relative===SCHEDULE)for(const task of Object.values(value.tables.tasks))task.status='inactive';
  if(relative===WORKSPACE){
   for(const [id,row] of Object.entries(value.tables.workspaces)){
    if(state.externalWorkspaces.has(id))delete value.tables.workspaces[id];
    else{row.path=rebind(row.path,sourceRoot,destination);row.sessionIds=row.sessionIds.filter(id=>!state.externalSessions.has(id));}
   }
   value.global.workspaceIds=value.global.workspaceIds.filter(id=>!state.externalWorkspaces.has(id));
   if(state.externalWorkspaces.has(value.global.defaultWorkspaceId))delete value.global.defaultWorkspaceId;
   if(state.externalWorkspaces.has(value.global.pendingMutation?.workspaceId))delete value.global.pendingMutation;
   for(const key of ['archivedSessionIds','pinnedSessionIds'])if(Array.isArray(value.global[key]))value.global[key]=value.global[key].filter(id=>!state.externalSessions.has(id));
  }
  if(relative.endsWith('/qx-route.json')||relative.endsWith('/content-watch/session.json')){write(root,relative,{});continue;}
  write(root,relative,value);
 }
 if(state.sessions.length){
  const rebuilt=path.join(root,'.local','restore-sessions-'+crypto.randomUUID());
  fs.mkdirSync(rebuilt,{recursive:true,mode:0o700});
  await withPersistence(state.lib,rebuilt,state.compression,async store=>{
   for(const old of state.sessions){
    if(state.externalSessions.has(old.header.id))continue;
    const header={...old.header,...(old.header.cwd===undefined?{}:{cwd:rebind(old.header.cwd,sourceRoot,destination)})};
    const session=state.lib.Session.fromRestore(header.id,old.events,header,old.inheritedEventCount,old.eventState,state.lib.currentSessionMessageProjections);
    for(const target of ['next-step','next-turn'])if(old.inbox[target].length)session.append('agent/inbox/spliced',{target,start:0,removedCount:old.inbox[target].length,inserted:[],outcome:'canceled'});
    const handle=await store.create(header,{inheritedEventCount:old.inheritedEventCount});
    try{await handle.append(session.snapshotEvents());await handle.flush();}finally{await handle.close();}
   }
  });
  // The original compressed logs are retained byte-for-byte outside the runtime session root.
  const saved=preserve(root,SESSIONS,true);originals.push(saved);fs.renameSync(rebuilt,path.join(root,SESSIONS));
 }
 const pending=state.pending.map(item=>({...item,decision:decisions[item.id]??'hold',restricted:true}));
 for(const item of pending)if(item.decision==='draft'){
  let relative='workspace/drafts/恢复待办-'+item.id.replace(':','-')+'.md';if(fs.existsSync(path.join(root,relative)))relative=relative.slice(0,-3)+'-'+crypto.randomUUID()+'.md';
  const file=path.join(root,relative);plain(file);fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});
  fs.writeFileSync(file,'# '+item.label+'\n\n这是从恢复副本提取的独立草稿，尚未调用模型、提交任务或发送消息。请人工核查原任务的提交状态。\n\n'+taskText(state.details.get(item.id))+'\n',{flag:'wx',mode:0o600});drafts.push(relative);item.draft=relative;
 }
 const history=state.previous?[...(state.previous.history??[]),{preparedAt:state.previous.preparedAt,pending:state.previous.pending,originals:state.previous.originals}]:[];
 write(root,PENDING,{schema:1,preparedAt:new Date().toISOString(),pending:pending.map(item=>({...item,text:taskText(state.details.get(item.id))})),originals,history});
 return {...publicResult(state),pending,drafts};
}
module.exports={inspectRestoredState,prepareRestoredState};
