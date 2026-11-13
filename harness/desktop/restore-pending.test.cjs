const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url');
const moduleFile=path.join(__dirname,'restore-pending.cjs');
const api=()=>require(moduleFile);
const payload=process.env.QX_RESTORE_TEST_PAYLOAD;
function write(root,file,data){const p=path.join(root,file);fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,JSON.stringify(data)+'\n');}
function read(root,file){return JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));}
function fixture(t){const temp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-restore-pending-'));t.after(()=>fs.rmSync(temp,{recursive:true,force:true}));const root=path.join(temp,'stage'),sourceRoot=path.join(temp,'original'),destination=path.join(temp,'enabled');fs.mkdirSync(root,{recursive:true});fs.mkdirSync(sourceRoot,{recursive:true});return {root,sourceRoot,destination,payload};}
const wechat='.local/dsh-home/qx-wechat/qx-pending.json',content='.local/content-watch/state.json',schedule='.local/dsh-home/storages/schedule.json';
function queues(root){
 write(root,wechat,{version:1,pending:[{id:'wx1',items:[{id:'m1',text:'待处理微信资料'}]}],active:{id:'wx2',items:[{id:'m2',text:'已提交结果未确认'}]},failed:[{id:'wf',items:[{id:'m3',text:'失败待核查'}]}],history:[{id:'old',status:'completed'}]});
 write(root,content,{version:1,profile:{direction:'合成业务',clients:'合成客户'},enabled:true,active:{id:'c1',phase:'submitting',messageId:'submitted'},lastReport:{id:'c1',content:'既有报告',pending:true,submitted:true,path:'keep-later'},drafts:{c1:{messageId:'submitted'}},status:'running'});
 write(root,schedule,{unit:{name:'schedule',version:1},global:null,tables:{tasks:{s1:{sessionId:'case',record:{id:'s1',title:'合成提醒',prompt:'核查附件',kind:'at',scheduledAt:'2030-01-01T00:00:00.000Z'},status:'active',lastDelivery:{scheduledAt:'2026-01-01T00:00:00.000Z',deliveredAt:'2026-01-01T00:00:00.000Z',messageId:'sent'}}}}});
}
test('restoration exposes a dedicated pending-state API',()=>{assert.ok(fs.existsSync(moduleFile),'restore-pending module must exist');assert.equal(typeof api().inspectRestoredState,'function');assert.equal(typeof api().prepareRestoredState,'function');});
test('freezes every queue, retains originals and records hold/draft/cancel without dispatch',async t=>{
 const opts=fixture(t);queues(opts.root);const original=fs.readFileSync(path.join(opts.root,wechat));
 const inspected=await api().inspectRestoredState(opts);assert.equal(inspected.pending.length,6);assert.equal(new Set(inspected.pending.map(p=>p.id)).size,6);
 assert.deepEqual(fs.readFileSync(path.join(opts.root,wechat)),original);
 const decisions={};decisions[inspected.pending.find(p=>p.kind==='wechat'&&p.status==='pending').id]='draft';decisions[inspected.pending.find(p=>p.kind==='schedule').id]='cancel';
 const done=await api().prepareRestoredState({...opts,decisions});assert.equal(done.drafts.length,1);
 assert.deepEqual(read(opts.root,wechat).pending,[]);assert.equal(read(opts.root,wechat).active,null);assert.equal(read(opts.root,wechat).history[0].status,'completed');
 assert.equal(read(opts.root,content).enabled,false);assert.equal(read(opts.root,content).active,null);assert.equal(read(opts.root,content).lastReport.pending,false);assert.equal(read(opts.root,content).lastReport.submitted,true);assert.equal(read(opts.root,content).lastReport.content,'既有报告');
 assert.equal(read(opts.root,schedule).tables.tasks.s1.status,'inactive');assert.equal(read(opts.root,schedule).tables.tasks.s1.lastDelivery.messageId,'sent');
 assert.equal(fs.readFileSync(path.join(opts.root,'.local/restore-original',wechat)).compare(original),0);
 assert.match(fs.readFileSync(path.join(opts.root,done.drafts[0]),'utf8'),/待处理微信资料/);assert.match(done.drafts[0],/^workspace\/drafts\//);
 assert.equal(read(opts.root,'.local/restore-pending.json').pending.find(p=>p.kind==='schedule').decision,'cancel');
});
test('rejects unknown formats and invalid decisions before changing any file',async t=>{
 const opts=fixture(t);queues(opts.root);const before=fs.readFileSync(path.join(opts.root,wechat));
 await assert.rejects(api().prepareRestoredState({...opts,decisions:{unexpected:'draft'}}),/RESTORE_PENDING_DECISION/);
 assert.deepEqual(fs.readFileSync(path.join(opts.root,wechat)),before);
 write(opts.root,schedule,{tasks:[]});await assert.rejects(api().inspectRestoredState(opts),/RESTORE_PENDING_FORMAT/);
});
test('rebinding changes only recognized workspace paths and refuses escapes',async t=>{
 const opts=fixture(t),old=path.join(opts.sourceRoot,'workspace'),external=old+'-other';
 write(opts.root,'.local/dsh-home/storages/workspace.json',{unit:{name:'workspace',version:2},global:{initialized:true,workspaceIds:['a','b']},tables:{workspaces:{a:{path:old,title:old,sessionIds:[],createdAt:'now',updatedAt:'now'},b:{path:external,title:'external',sessionIds:[],createdAt:'now',updatedAt:'now'}}}});
 const inspection=await api().inspectRestoredState(opts);assert.equal(inspection.pending.filter(p=>p.kind==='external-workspace').length,1);
 await api().prepareRestoredState(opts);const workspaces=read(opts.root,'.local/dsh-home/storages/workspace.json').tables.workspaces;
 assert.equal(workspaces.a.path,path.join(opts.destination,'workspace'));assert.equal(workspaces.a.title,old);assert.equal(workspaces.b,undefined);
 assert.deepEqual(read(opts.root,'.local/dsh-home/storages/workspace.json').global.workspaceIds,['a']);
 assert.equal(read(opts.root,'.local/restore-original/.local/dsh-home/storages/workspace.json').tables.workspaces.b.path,external);
 await assert.rejects(api().prepareRestoredState({...opts,root:opts.sourceRoot}),/RESTORE_PENDING_SOURCE/);
});
test('previews are bounded and redact likely credentials',async t=>{
 const opts=fixture(t);write(opts.root,wechat,{version:1,pending:[{id:'x',token:'hidden',items:[{text:'api_key=sk-secret-value '+ 'a'.repeat(2000)}]}],active:null,failed:[],history:[]});
 const result=await api().inspectRestoredState(opts);assert.ok(result.pending[0].preview.length<=500);assert.doesNotMatch(result.pending[0].preview,/sk-secret-value|hidden/);
});
test('a later restore preserves previous pending decisions and full held draft text',async t=>{
 const opts=fixture(t);write(opts.root,wechat,{version:1,pending:[{id:'x',items:[{text:'开头'+ '甲'.repeat(600)+'结尾'}]}],active:null,failed:[],history:[]});
 const first=await api().prepareRestoredState(opts),id=first.pending[0].id;
 const second=await api().inspectRestoredState(opts);assert.equal(second.pending[0].id,id);
 const done=await api().prepareRestoredState({...opts,decisions:{[id]:'draft'}});
 assert.match(fs.readFileSync(path.join(opts.root,done.drafts[0]),'utf8'),/结尾/);
 await api().prepareRestoredState(opts);const ledger=read(opts.root,'.local/restore-pending.json');assert.ok(ledger.history.some(row=>row.pending.some(item=>item.id===id&&item.decision==='draft')));
});
test('unknown session files fail visibly rather than disappearing from the task inventory',async t=>{
 const opts=fixture(t);write(opts.root,'.local/dsh-home/sessions/unrecognized.json',{pending:['work']});
 await assert.rejects(api().inspectRestoredState(opts),/RESTORE_PENDING_SESSION_FORMAT/);
});
test('an existing null or primitive queue is not mistaken for an absent file',async t=>{
 const opts=fixture(t);for(const malformed of [null,false,0,'']){write(opts.root,wechat,malformed);await assert.rejects(api().inspectRestoredState(opts),/RESTORE_PENDING_FORMAT/);}
});
test('real queue consumers do not replay restored work when connected or ticked',async t=>{
 const opts=fixture(t);queues(opts.root);const state=read(opts.root,content);state.seen=[];write(opts.root,content,state);
 await api().prepareRestoredState(opts);let calls=0;
 const {MessageCoalescer}=await import('../plugins/wechat/qx-coalescer.js');
 const q=new MessageCoalescer({state:read(opts.root,wechat),persist:async()=>{},process:async()=>{calls++;}});await q.recover();q.resume();await q.flush();await q.idle();q.pause();assert.equal(calls,0);
 const {createContentWatch}=await import('../plugins/content-watch/core.mjs');
 const watch=await createContentWatch({stateDir:path.join(opts.root,'.local/content-watch'),client:{checkLogin:async()=>{calls++;}},deliver:async()=>{calls++;}});
 try{await watch.tick();assert.equal(calls,0);}finally{await watch.dispose();}
});
async function libs(){const req=createRequire(path.join(payload,'package.json')),load=name=>import(pathToFileURL(req.resolve('@deepseek-ai/'+name)).href);return {load,...await load('cordis'),...await load('dsh-session'),persistence:await load('dsh-session-persistence-jsonl'),...await load('dsh-session-format-catalog')};}
async function offline(lib,root,compression,run){const ctx=new lib.Context(),fiber=ctx.plugin(lib.persistence,{root,compression});try{await fiber.await();return await run(ctx.sessionPersistence);}finally{await fiber.dispose();}}
test('fixed Harness zstd: clear inbox by appended events; preserve original and message content; restore new cwd', {skip:!payload},async t=>{
 const opts=fixture(t),lib=await libs(),sourceSessions=path.join(opts.sourceRoot,'.local/dsh-home/sessions'),oldCwd=path.join(opts.sourceRoot,'workspace'),id='case/中文';
 const session=new lib.Session(id,undefined,{version:lib.SESSION_FORMAT_VERSION,id,cwd:oldCwd,createdAt:Date.now(),isSeeded:false,delegationDepth:0});
 session.append('agent/inbox/spliced',{target:'next-turn',start:0,inserted:[{id:'m1',role:'user',content:[{type:'text',text:'literal '+oldCwd}],source:{kind:'user'}}]});
 session.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[{id:'m2',role:'user',content:[{type:'text',text:'second '+oldCwd}],source:{kind:'user'}}]});
 const events=session.snapshotEvents();await offline(lib,sourceSessions,'zstd',async store=>{const handle=await store.create(session.header);try{await handle.append(events);await handle.flush();}finally{await handle.close();}});
 const before=treeDigest(opts.sourceRoot);fs.cpSync(opts.sourceRoot,opts.root,{recursive:true});
 const inspected=await api().inspectRestoredState(opts);assert.equal(inspected.pending.filter(p=>p.kind==='session-inbox').length,2);assert.deepEqual(treeDigest(opts.sourceRoot),before);
 const result=await api().prepareRestoredState({...opts,decisions:Object.fromEntries(inspected.pending.map(p=>[p.id,'hold']))});assert.equal(result.pending.length,2);assert.deepEqual(treeDigest(opts.sourceRoot),before);
 await offline(lib,path.join(opts.root,'.local/dsh-home/sessions'),'zstd',async store=>{
   const listing=await store.list();assert.equal(listing.length,1);assert.equal(listing[0].header.cwd,path.join(opts.destination,'workspace'));assert.ok(listing[0].location.path.includes('enabled-workspace'));
   const handle=await store.open(id,'read');try{const {events:after}=await handle.read();assert.deepEqual(after.slice(0,events.length),events);const inbox={'next-turn':[],'next-step':[]};for(const e of after){if(e.type==='agent/inbox/spliced')inbox[e.data.target].splice(e.data.start,e.data.removedCount||0,...e.data.inserted);}assert.deepEqual(inbox,{'next-turn':[],'next-step':[]});assert.equal(after.filter(e=>e.type==='agent/inbox/spliced'&&e.data.outcome==='canceled').length,2);}finally{await handle.close();}
   const resumed=await store.open(id,'write');try{
    const before=await resumed.read(),next=lib.Session.fromRestore(id,before.events,resumed.header,resumed.inheritedEventCount,before.eventState,[]);
    next.append('agent/inbox/spliced',{target:'next-turn',start:0,inserted:[{id:'fresh-followup',role:'user',content:[{type:'text',text:'仅处理新指令'}],source:{kind:'user'}}]});
    await resumed.append(next.snapshotEvents(before.events.length));const after=await resumed.read(),queues={'next-turn':[],'next-step':[]};
    for(const e of after.events)if(e.type==='agent/inbox/spliced')queues[e.data.target].splice(e.data.start,e.data.removedCount||0,...e.data.inserted);
    assert.deepEqual(queues['next-turn'].map(m=>m.id),['fresh-followup']);assert.deepEqual(queues['next-step'],[]);
   }finally{await resumed.close();}
 });
});
test('fixed Harness external-cwd sessions and dependent routing stay quarantined', {skip:!payload},async t=>{
 const opts=fixture(t),lib=await libs(),sessions=path.join(opts.root,'.local/dsh-home/sessions');
 const id='outside',cwd=path.join(path.dirname(opts.root),'unselected-original-folder');
 const session=new lib.Session(id,undefined,{version:lib.SESSION_FORMAT_VERSION,id,cwd,createdAt:Date.now(),isSeeded:false,delegationDepth:0});
 await offline(lib,sessions,'none',async store=>{const h=await store.create(session.header);try{await h.flush();}finally{await h.close();}});
 write(opts.root,'.local/dsh-home/qx-wechat/qx-route.json',{sessionId:id});
 const preview=await api().inspectRestoredState(opts);assert.equal(preview.pending.filter(p=>p.kind==='external-workspace').length,1);
 await api().prepareRestoredState(opts);assert.deepEqual(read(opts.root,'.local/dsh-home/qx-wechat/qx-route.json'),{});
 await offline(lib,sessions,'none',async store=>assert.deepEqual(await store.list(),[]));
 await offline(lib,path.join(opts.root,'.local/restore-original',SESSIONS_TEST),'none',async store=>{const saved=await store.list();assert.equal(saved[0].header.cwd,cwd);});
});
test('fixed Harness schedule backend freezes actual global-null storage and keeps delivery receipt', {skip:!payload},async t=>{
 const opts=fixture(t),lib=await libs(),{JsonStorageBackend}=await lib.load('dsh-storage-json'),{scheduleDomain,createAtScheduleRecord}=await lib.load('dsh-schedule');
 const storageRoot=path.join(opts.root,'.local/dsh-home/storages'),descriptor={name:'schedule',version:1,tables:['tasks'],hasGlobal:false};
 const backend=new JsonStorageBackend(storageRoot),unit=await backend.kv.open(descriptor);
 const record=createAtScheduleRecord('real-task','本轮须保留的完整提醒正文','2030-01-01T00:00:00.000Z',Date.now(),'真实固定库合成提醒');
 try{await unit.putRecord('tasks',record.id,{sessionId:'case',record,status:'active'});}finally{await backend.close();}
 assert.equal(read(opts.root,schedule).global,null);const preview=await api().inspectRestoredState(opts);assert.match(preview.pending[0].preview,/完整提醒正文/);
 const result=await api().prepareRestoredState({...opts,decisions:{[preview.pending[0].id]:'draft'}});assert.match(fs.readFileSync(path.join(opts.root,result.drafts[0]),'utf8'),/完整提醒正文/);
 const reopened=new JsonStorageBackend(storageRoot);try{const checked=await (await reopened.kv.open(descriptor)).loadAll();const task=scheduleDomain.tables.tasks.valueSchema.parse(checked.tables.tasks[record.id]);assert.equal(task.status,'inactive');assert.deepEqual(task.record,record);}finally{await reopened.close();}
});
const SESSIONS_TEST='.local/dsh-home/sessions';
function treeDigest(root){const result={};function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,entry.name);if(entry.isDirectory())walk(file);else result[path.relative(root,file)]=require('node:crypto').createHash('sha256').update(fs.readFileSync(file)).digest('hex');}}walk(root);return result;}
