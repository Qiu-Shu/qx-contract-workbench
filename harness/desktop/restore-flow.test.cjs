const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url');
const {createBackupController}=require('./backup-controller.cjs'),runtime=require('./backup-runtime.cjs');
const installed=require('./installed-runtime.cjs'),locations=require('./data-location.cjs'),{stopInstalledHost}=require('./installed-stop.cjs');
const enabled=process.platform==='win32'&&process.env.QX_RESTORE_FLOW==='1';
const fixed=process.env.QX_TEST_APP,zip=process.env.QX_TEST_RESTIC_ZIP;
const evidence=process.env.QX_RESTORE_FLOW_EVIDENCE||'D:/CodexChecks/AI-Shixiong-restore-activation-20261113/pending';
const password='synthetic-native-restore-flow-only-2026';
const wx='.local/dsh-home/qx-wechat/qx-pending.json',cw='.local/content-watch/state.json',sc='.local/dsh-home/storages/schedule.json';
function put(root,name,value){const file=path.join(root,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,typeof value==='string'?value:JSON.stringify(value,null,2)+'\n');}
const read=(root,name)=>JSON.parse(fs.readFileSync(path.join(root,name),'utf8'));
const digest=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function tree(root){const result={};function visit(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,entry.name);if(entry.isSymbolicLink()){result[path.relative(root,file)]='LINK:'+fs.readlinkSync(file);continue;}if(entry.isDirectory())visit(file);else result[path.relative(root,file)]=digest(file);}}visit(root);return result;}
function protectedFiles(root){return Object.fromEntries(require('./backup-preparation.cjs').inspectScope(root).files.map(file=>{const target=path.join(root,file.path);return [file.path,{sha256:digest(target),mtimeNs:fs.statSync(target,{bigint:true}).mtimeNs.toString()}];}));}
function safeRemove(root){const resolved=path.resolve(root),base=path.resolve(evidence);assert.ok(resolved.startsWith(base+path.sep));assert.match(path.basename(resolved),/^flow-fixture-/);fs.rmSync(resolved,{recursive:true,force:true});}
function payloadFixture(root){
 const payload=path.join(root,'payload'),source=path.resolve(__dirname,'..'),stage=require('../packaging/stage.cjs'),manifest=[];
 fs.mkdirSync(payload,{recursive:true});
 for(const folder of ['bridge','plugins','legacy','workspace-seed']){fs.mkdirSync(path.join(payload,folder));stage.overlay(path.join(source,folder),path.join(payload,folder),manifest,folder);}
 fs.mkdirSync(path.join(payload,'config'));stage.overlay(path.join(source,'packaging/payload-config'),path.join(payload,'config'),manifest,'config');
 stage.copyBackupConfiguration(source,payload,manifest);stage.copyDesktopRunners(source,payload,manifest);
 // Runtime executables have real parent directories: production validates every path ancestor.
 fs.mkdirSync(path.join(payload,'runtime'));fs.copyFileSync(path.join(fixed,'runtime/node.exe'),path.join(payload,'runtime/node.exe'));
 fs.cpSync(path.join(fixed,'runtime/python'),path.join(payload,'runtime/python'),{recursive:true,filter:file=>!file.includes('__pycache__')});
 fs.symlinkSync(path.join(fixed,'node_modules'),path.join(payload,'node_modules'),'junction');
 const id=crypto.createHash('sha256').update(JSON.stringify(manifest)).digest('hex');put(payload,'config/initialization.json',{schema:1,id});
 return payload;
}
async function seedSession(data,payload){
 const req=createRequire(path.join(payload,'package.json')),load=name=>import(pathToFileURL(req.resolve('@deepseek-ai/'+name)).href);
 const [{Context},{Session,SESSION_FORMAT_VERSION},persistence]=await Promise.all([load('cordis'),load('dsh-session'),load('dsh-session-persistence-jsonl')]);
 const ctx=new Context(),fiber=ctx.plugin(persistence,{root:path.join(data,'.local/dsh-home/sessions'),compression:'zstd'});
 try{await fiber.await();const id='flow-session',session=new Session(id,undefined,{version:SESSION_FORMAT_VERSION,id,cwd:path.join(data,'workspace'),createdAt:Date.now(),isSeeded:false,delegationDepth:0});
  session.append('agent/inbox/spliced',{target:'next-turn',start:0,inserted:[{id:'flow-old-message',role:'user',content:[{type:'text',text:'合成会话旧待办，正文保留 '+data}],source:{kind:'user'}}]});
  session.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[{id:'flow-old-step',role:'user',content:[{type:'text',text:'合成会话旧步骤'}],source:{kind:'user'}}]});
  const handle=await ctx.sessionPersistence.create(session.header);try{await handle.append(session.snapshotEvents());await handle.flush();}finally{await handle.close();}
 }finally{await fiber.dispose();}
}
function seedBusiness(data){
 put(data,'workspace/合成原材料.txt','Synthetic material only. 恢复后必须字节一致。');
 put(data,'.local/dsh-home/.credentials.yaml','synthetic-secret-not-to-be-restored');
 put(data,'.local/desktop-data/model-settings.enc','synthetic-encrypted-secret-not-to-be-restored');
 put(data,'.local/content-watch/connection.json',{provider:'synthetic',token:'synthetic-content-secret'});
 put(data,'.local/content-watch/auth/cookies.json',[{value:'synthetic-cookie-secret'}]);
 put(data,'.local/desktop-data/locale.json',{locale:'zh-CN'});
 put(data,wx,{version:1,pending:[{id:'flow-wx',items:[{id:'wx-message',text:'请核查合成附件，只转成恢复草稿'}]}],active:null,failed:[],history:[{id:'old-done',status:'completed'}]});
 put(data,'.local/dsh-home/qx-wechat/qx-route.json',{sessionId:'flow-session'});
 const reportId='11111111-1111-4111-8111-111111111111',reportPath=path.join(data,'.local/content-watch/reports',reportId+'.md');
 put(data,cw,{version:1,profile:{practice:'合成业务',targetClients:'合成客户'},enabled:true,nextRunAt:0,lastRunAt:null,seen:[],drafts:{},active:{id:reportId,phase:'submitting',messageId:'flow-submitted'},status:'running',lastReport:{id:reportId,path:reportPath,content:'已取得的合成报告',pending:true,submitted:true}});
 put(data,'.local/content-watch/reports/'+reportId+'.md','已取得的合成报告');put(data,'.local/content-watch/reports/'+reportId+'.json',{id:reportId,items:[]});
 put(data,sc,{unit:{name:'schedule',version:1},global:null,tables:{tasks:{'flow-reminder':{sessionId:'flow-session',record:{id:'flow-reminder',kind:'at',title:'合成提醒',prompt:'不得自动重放的提醒',scheduledAt:'2030-01-01T00:00:00.000Z'},status:'active'}}}});
 put(data,'.local/dsh-home/storages/workspace.json',{unit:{name:'workspace',version:2},global:{initialized:true,workspaceIds:['flow-space'],archivedSessionIds:[],pinnedSessionIds:[]},tables:{workspaces:{'flow-space':{path:path.join(data,'workspace'),title:'合成工作区',sessionIds:['flow-session'],createdAt:'2026-11-13T00:00:00.000Z',updatedAt:'2026-11-13T00:00:00.000Z'}}}});
}
function stopped(data){put(data,'.local/runtime.json',{hostPid:null,launcherPid:process.pid});put(data,'.local/host-state.json',{phase:'stopped',hostPid:null,launcherPid:process.pid});}
function credentialFree(root){
 for(const file of ['.local/dsh-home/.credentials.yaml','.local/desktop-data/model-settings.enc','.local/content-watch/connection.json','.local/content-watch/auth/cookies.json'])assert.equal(fs.existsSync(path.join(root,file)),false,file);
 for(const [file,value] of Object.entries(tree(root)))if(!value.startsWith('LINK:'))assert.doesNotMatch(fs.readFileSync(path.join(root,file),'utf8'),/synthetic-(?:secret-not|encrypted-secret|content-secret|cookie-secret)/,file);
}
async function assertFrozenConsumers(data,payload,source){
 const req=createRequire(path.join(payload,'package.json')),load=name=>import(pathToFileURL(req.resolve('@deepseek-ai/'+name)).href);
 const [{Context},persistence]=await Promise.all([load('cordis'),load('dsh-session-persistence-jsonl')]);
 const ctx=new Context(),fiber=ctx.plugin(persistence,{root:path.join(data,'.local/dsh-home/sessions'),compression:'zstd'});
 try{await fiber.await();const list=await ctx.sessionPersistence.list();assert.equal(list.length,1);assert.equal(list[0].header.cwd,path.join(data,'workspace'));
  const handle=await ctx.sessionPersistence.open('flow-session','read');try{const {events}=await handle.read(),inbox={'next-turn':[],'next-step':[]};for(const event of events)if(event.type==='agent/inbox/spliced')inbox[event.data.target].splice(event.data.start,event.data.removedCount||0,...event.data.inserted);
   assert.deepEqual(inbox,{'next-turn':[],'next-step':[]});assert.equal(events[0].data.inserted[0].content[0].text,'合成会话旧待办，正文保留 '+source);
  }finally{await handle.close();}
 }finally{await fiber.dispose();}
 let calls=0;
 const {MessageCoalescer}=await import(pathToFileURL(path.join(payload,'plugins/wechat/qx-coalescer.js')).href);
 const queue=new MessageCoalescer({state:read(data,wx),persist:async()=>{},process:async()=>{calls++;}});await queue.recover();queue.resume();await queue.flush();await queue.idle();queue.pause();
 const {createContentWatch}=await import(pathToFileURL(path.join(payload,'plugins/content-watch/core.mjs')).href);
 const watch=await createContentWatch({stateDir:path.join(data,'.local/content-watch'),client:{checkLogin:async()=>{calls++;}},deliver:async()=>{calls++;}});
 try{await watch.tick();assert.equal(calls,0);}finally{await watch.dispose();}
 assert.equal(read(data,sc).tables.tasks['flow-reminder'].status,'inactive');return calls;
}
async function action(controller,name,input){const result=await controller.act(name,input);assert.equal(result.ok,true,name+': '+(await controller.state()).error);return controller.state();}
async function choose(controller,kind){assert.equal((await controller.choose(kind)).ok,true,'choose '+kind);}
function noAutomaticConnect(entries){for(const entry of entries){if(entry.id==='qx-personal-wechat')assert.equal(entry.config.autoConnect,false);if(Array.isArray(entry.insert))noAutomaticConnect(entry.insert);}}

test('native Windows encrypted desktop restore: review, prepare, initialize, select, drafts, rollback and repeat',{skip:!enabled,timeout:600000},async t=>{
 assert.ok(fixed&&zip,'Set QX_TEST_APP and QX_TEST_RESTIC_ZIP to fixed verified prerequisites');fs.mkdirSync(evidence,{recursive:true});
 const root=fs.mkdtempSync(path.join(evidence,'flow-fixture-')),payload=payloadFixture(root),data=path.join(root,'original'),picks={};
 for(const kind of ['backupParent','restoreParent','activationParent']){picks[kind]=path.join(root,kind);fs.mkdirSync(picks[kind]);}
 const trace=[],summary={root,payload,source:data,node:process.version,syntheticOnly:true,modelRequests:0,externalMessages:0,checkpoints:[]};
 const checkpoint=(name,details={})=>{summary.checkpoints.push({name,at:new Date().toISOString(),...details});put(evidence,'flow-latest.json',summary);};
 t.after(()=>{checkpoint('test-finished');if(process.env.QX_RESTORE_FLOW_KEEP!=='1')safeRemove(root);});
 installed.initialize(payload,data);seedBusiness(data);await seedSession(data,payload);stopped(data);
 assert.equal(read(data,'.local/initialized-payload.json').schema,2);checkpoint('source-initialized');
 const originalMaterial=digest(path.join(data,'workspace/合成原材料.txt')),originalSecret=digest(path.join(data,'.local/dsh-home/.credentials.yaml')),originalProtected=protectedFiles(data);
 function controllerFor(target){return createBackupController({anchor:data,data:target,payload,
  pick:async kind=>picks[kind],credentialStatus:async()=>({modelConfigured:false,wechatConnected:false}),setMaintenance:value=>trace.push(['maintenance',value]),
  stop:async()=>{stopped(target);await stopInstalledHost(target);trace.push(['stop',target]);},resume:async()=>trace.push(['resume']),relaunch:()=>trace.push(['relaunch']),openDrafts:async folder=>trace.push(['drafts',folder]),
  prepareEngine:()=>runtime.prepareEngine({anchor:data,payload,fetcher:async()=>new Response(fs.readFileSync(zip))})});}
 const controller=controllerFor(data);
 await action(controller,'prepareEngine');assert.equal(runtime.engineReady(data),true);checkpoint('engine-prepared-from-verified-cache');
 await action(controller,'pause',{confirm:true});await choose(controller,'backupParent');
 const backup=await action(controller,'backup',{password,passwordConfirm:password});assert.match(backup.lastResult.snapshotId,/^[a-f0-9]{64}$/);checkpoint('restic-backup-readback',{files:backup.lastResult.fileCount,bundle:backup.lastResult.bundle});
 picks.bundle=backup.lastResult.bundle;await choose(controller,'bundle');await choose(controller,'restoreParent');const restored=await action(controller,'restore',{password});const reviewRoot=restored.lastResult.destination;
 credentialFree(reviewRoot);const restoredBefore=tree(reviewRoot);checkpoint('restic-restored',{reviewRoot});
 assert.throws(()=>installed.initialize(payload,reviewRoot),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
 const inspected=await action(controller,'review');assert.ok(inspected.review.pending.length>=5);assert.equal(inspected.review.reauthorization.length,4);
 const decisions=Object.fromEntries(inspected.review.pending.map(item=>[item.id,item.kind==='wechat'?'draft':item.kind==='schedule'?'cancel':'hold']));
 await choose(controller,'activationParent');const preparedState=await action(controller,'prepare',{reviewToken:inspected.review.reviewToken,applySettings:true,decisions});const prepared=preparedState.prepared.destination;
 checkpoint('prepared',{prepared,pending:preparedState.prepared.pending.length,drafts:preparedState.prepared.drafts.length});
 assert.deepEqual(tree(reviewRoot),restoredBefore);credentialFree(prepared);assert.equal(read(prepared,'.local/restore-activation.json').phase,'prepared');
 assert.throws(()=>installed.initialize(payload,prepared),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});assert.throws(()=>locations.selectDataLocation(data,prepared),{code:'LOCATION_RESTORE_NOT_READY'});
 assert.equal(read(prepared,wx).pending.length,0);assert.equal(read(prepared,cw).enabled,false);assert.equal(read(prepared,cw).active,null);assert.equal(read(prepared,cw).lastReport.submitted,true);assert.equal(read(prepared,cw).lastReport.pending,false);assert.ok(read(prepared,cw).lastReport.path.startsWith(prepared+path.sep));assert.equal(read(prepared,sc).tables.tasks['flow-reminder'].status,'inactive');
 const ledger=read(prepared,'.local/restore-pending.json');assert.ok(ledger.pending.every(item=>item.restricted===true));assert.equal(ledger.pending.find(item=>item.kind==='schedule').decision,'cancel');assert.equal(preparedState.prepared.drafts.length,1);
 for(const draft of preparedState.prepared.drafts)assert.match(fs.readFileSync(path.join(prepared,draft),'utf8'),/合成附件/);
 await action(controller,'openDrafts');assert.equal(trace.at(-1)[0],'drafts');assert.equal(fs.statSync(trace.at(-1)[1]).isDirectory(),true);
 await action(controller,'activate',{confirm:true});assert.equal(read(prepared,'.local/restore-activation.json').phase,'ready');assert.equal(locations.resolveDataLocation(data).data,prepared);assert.equal(trace.at(-1)[0],'relaunch');
 credentialFree(prepared);noAutomaticConnect(read(prepared,'.local/dsh-home/profiles/web/cordis.patch.yml'));assert.equal(digest(path.join(prepared,'workspace/合成原材料.txt')),originalMaterial);checkpoint('ready-selected-with-credentials-disconnected');
 const consumerCalls=await assertFrozenConsumers(prepared,payload,data);checkpoint('ready-real-consumers-remain-frozen',{consumerCalls});
 const auditBefore=tree(path.join(prepared,'.local/restore-original'));await action(controller,'rollback',{confirm:true});assert.equal(locations.resolveDataLocation(data).data,data);checkpoint('rollback-selected-original');
 assert.equal(digest(path.join(data,'workspace/合成原材料.txt')),originalMaterial);assert.equal(digest(path.join(data,'.local/dsh-home/.credentials.yaml')),originalSecret);

 // Back up the initialized restored copy again: retained audit and pending history must remain admissible.
 const repeated=controllerFor(prepared);await action(repeated,'pause',{confirm:true});await choose(repeated,'backupParent');const backup2=await action(repeated,'backup',{password,passwordConfirm:password});checkpoint('repeat-backup-readback',{files:backup2.lastResult.fileCount,bundle:backup2.lastResult.bundle});
 picks.bundle=backup2.lastResult.bundle;await choose(repeated,'bundle');await choose(repeated,'restoreParent');await action(repeated,'restore',{password});const review2=await action(repeated,'review');await choose(repeated,'activationParent');
 const decisions2=Object.fromEntries(review2.review.pending.map(item=>[item.id,'hold']));const ready2=await action(repeated,'prepare',{reviewToken:review2.review.reviewToken,applySettings:false,decisions:decisions2});
 assert.notEqual(ready2.prepared.destination,prepared);assert.deepEqual(tree(path.join(prepared,'.local/restore-original')),auditBefore);assert.ok(Object.keys(tree(path.join(ready2.prepared.destination,'.local/restore-original'))).length>Object.keys(auditBefore).length);checkpoint('repeat-retained-old-audit',{secondPrepared:ready2.prepared.destination});
 const selectorBefore=fs.readFileSync(path.join(data,'.local/data-location.json'));put(ready2.prepared.destination,'workspace/合成原材料.txt','tampered synthetic bytes');
 assert.equal((await repeated.act('activate',{confirm:true})).ok,false);assert.equal((await repeated.state()).error,'BACKUP_PREPARED_CHANGED');assert.deepEqual(fs.readFileSync(path.join(data,'.local/data-location.json')),selectorBefore);assert.equal(read(ready2.prepared.destination,'.local/restore-activation.json').phase,'prepared');checkpoint('tampered-prepared-cannot-select');
 const third=await action(repeated,'prepare',{reviewToken:review2.review.reviewToken,applySettings:false,decisions:decisions2});
 const initializationAsset=path.join(payload,'config/profile-package.json'),assetOriginal=fs.readFileSync(initializationAsset);
 try{fs.writeFileSync(initializationAsset,'invalid synthetic JSON');assert.equal((await repeated.act('activate',{confirm:true})).ok,false);assert.deepEqual(fs.readFileSync(path.join(data,'.local/data-location.json')),selectorBefore);assert.equal(read(third.prepared.destination,'.local/restore-activation.json').phase,'prepared');}
 finally{fs.writeFileSync(initializationAsset,assetOriginal);}
 checkpoint('failed-real-initialization-cannot-select',{prepared:third.prepared.destination});
 assert.equal(digest(path.join(data,'workspace/合成原材料.txt')),originalMaterial);assert.deepEqual(protectedFiles(data),originalProtected);assert.equal(t.signal.aborted,false);summary.result='passed';checkpoint('flow-passed',{unchangedProtectedFiles:Object.keys(originalProtected).length});
});
