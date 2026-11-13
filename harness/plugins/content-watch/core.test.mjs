import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm,utimes,stat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createContentWatch,INTERVAL_MS} from './core.mjs';

const item={id:'note-1',title:'企业用工常见问题',author:'合成作者',publishedAt:'2026-11-05T00:00:00Z',likes:100,comments:null,collected:20,shares:null,url:'https://www.xiaohongshu.com/explore/note-1',text:'合成正文：企业调整劳动岗位，应先了解合同约定和证据。',textCoverage:'正文',keywords:['企业用工']};
async function fixture(t,overrides={}){
  const stateDir=await mkdtemp(join(tmpdir(),'qx-content-watch-'));t.after(()=>rm(stateDir,{recursive:true,force:true}));
  let at=Date.parse('2026-11-05T04:00:00Z'),collects=0,deliveries=0,loggedIn=true;
  const client={checkLogin:async()=>({loggedIn}),loginQr:async()=>({img:'data:image/png;base64,eA=='}),collect:async()=>{collects++;return {items:[item,item],warnings:[]};}};
  const deliver=async report=>{deliveries++;return {sessionId:'qx-content-watch',content:'合成模型摘要：关注用工调整的程序与证据。'};};
  const service=await createContentWatch({stateDir,client,deliver,clock:()=>at,...overrides});
  return {service,stateDir,client,counts:()=>({collects,deliveries}),setTime:value=>{at=value;},time:()=>at,login:value=>{loggedIn=value;}};
}
const profile={practice:'劳动用工',targetClients:'中小企业负责人',enabled:true};

test('API credential and budget errors halt scheduled calls without asking for a QR scan',async t=>{
  for(const [code,status] of [['TOKEN_REQUIRED','token_required'],['TOKEN_INVALID','token_invalid'],['BUDGET_EXCEEDED','budget_exceeded'],['RATE_LIMIT','rate_limited'],['QUOTA_EXCEEDED','quota_exceeded'],['API_PERMISSION','provider_unavailable']]){
    let calls=0;const f=await fixture(t,{client:{checkLogin:async()=>{calls++;throw Object.assign(Error('secret upstream text'),{code});}}});
    await f.service.saveProfile(profile);await f.service.tick();await f.service.tick();
    assert.equal(f.service.status().status,status);assert.equal(calls,1);assert.doesNotMatch(f.service.status().message,/扫码|secret/);
  }
});
test('API local credential check is not presented as a verified remote login',async t=>{
  const f=await fixture(t,{client:{checkLogin:async()=>({loggedIn:true,verified:false})}});
  await f.service.checkLogin();assert.equal(f.service.status().login.verified,false);
  assert.match(f.service.status().message,/首次整理/);
});
test('collection receives seen IDs before selecting paid detail calls',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);await f.service.run();
  let options;f.client.collect=async(_p,o)=>{options=o;return {items:[]};};await f.service.run();
  assert.deepEqual(options.seenIds,[item.id]);
});
test('selected report topic drafts once, persists submission before queueing and rejects foreign IDs',async t=>{
  let submissions=0,observed;
  const f=await fixture(t,{draft:async(report,selected)=>{
    submissions++;assert.equal(selected.id,item.id);await report.onSubmitting({messageId:'synthetic-draft-message'});
    observed=JSON.parse(await readFile(join(f.stateDir,'state.json'),'utf8'));
    return {pending:true};
  }});
  await f.service.saveProfile(profile);await f.service.run();const report=f.service.status().lastReport;
  assert.equal(report.items[0].id,item.id);
  await assert.rejects(f.service.draft({reportId:report.id,itemId:'../../other'}),/选题/);
  await f.service.draft({reportId:report.id,itemId:item.id});
  assert.equal(Object.values(observed.drafts)[0].messageId,'synthetic-draft-message');
  await f.service.draft({reportId:report.id,itemId:item.id});assert.equal(submissions,1);
  assert.equal(f.service.status().scriptPending,false);
  const reopened=await createContentWatch({stateDir:f.stateDir,client:f.client,deliver:async()=>{},draft:async()=>{throw Error('duplicate');}});
  await reopened.draft({reportId:report.id,itemId:item.id});assert.equal(submissions,1);
});

test('first install is inactive; profile requires two bounded fields and persists trimmed values',async t=>{
  const f=await fixture(t);assert.equal(f.service.status().status,'unconfigured');
  await f.service.tick();assert.deepEqual(f.counts(),{collects:0,deliveries:0});
  await assert.rejects(f.service.saveProfile({...profile,practice:' '}),/业务方向/);
  await assert.rejects(f.service.saveProfile({...profile,targetClients:'x'.repeat(501)}),/目标客户/);
  await f.service.saveProfile({...profile,practice:' 劳动用工 '});
  const saved=JSON.parse(await readFile(join(f.stateDir,'state.json'),'utf8'));
  assert.equal(saved.profile.practice,'劳动用工');assert.equal(saved.enabled,true);assert.equal(saved.nextRunAt,f.time());
});

test('due runs once, preserves sources and schedules exactly 72 hours without timer drift',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);await f.service.tick();
  const state=f.service.status();assert.deepEqual(f.counts(),{collects:1,deliveries:1});
  assert.equal(state.nextRunAt,f.time()+72*3600000);assert.equal(INTERVAL_MS,72*3600000);
  assert.match(state.lastReport.content,/合成模型摘要/);assert.match(state.lastReport.content,/xiaohongshu\.com/);
  await f.service.tick();f.setTime(state.nextRunAt-1);await f.service.tick();assert.equal(f.counts().collects,1);
  f.setTime(state.nextRunAt);await f.service.tick();assert.equal(f.counts().collects,2);assert.equal(f.counts().deliveries,1,'old content is not dispatched twice');
});

test('concurrent manual and clock triggers share one collection',async t=>{
  let release;const gate=new Promise(r=>{release=r;});
  const f=await fixture(t);f.client.collect=async()=>{await gate;return {items:[item],warnings:[]};};
  await f.service.saveProfile(profile);const one=f.service.run(),two=f.service.tick();
  await new Promise(r=>setTimeout(r,10));assert.equal(f.service.status().status,'running');release();await Promise.all([one,two]);
  assert.equal(f.counts().deliveries,1);
});

test('pausing while a run acquires its lock remains paused in memory and on disk',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);
  const running=f.service.run(),paused=f.service.pause();await Promise.all([running,paused]);
  assert.equal(f.service.status().enabled,false);assert.equal(f.service.status().status,'paused');
  assert.equal(JSON.parse(await readFile(join(f.stateDir,'state.json'),'utf8')).enabled,false);
  f.setTime(f.time()+INTERVAL_MS);await f.service.tick();assert.equal(f.counts().collects,1);
});

test('pausing while a run reloads durable state is not replaced by the older enabled value',async t=>{
  let onRunStart,paused;
  const f=await fixture(t,{clock:()=>{
    if(onRunStart){const pause=onRunStart;onRunStart=null;queueMicrotask(pause);}
    return Date.parse('2026-11-05T04:00:00Z');
  }});
  await f.service.saveProfile(profile);
  // runImpl starts its readFile immediately after this clock call; the queued pause
  // runs while that read is outstanding, after the lock has already been acquired.
  onRunStart=()=>{paused=f.service.pause();};
  await f.service.run();await paused;
  assert.equal(f.service.status().enabled,false);assert.equal(f.service.status().status,'paused');
  assert.equal(JSON.parse(await readFile(join(f.stateDir,'state.json'),'utf8')).enabled,false);
});

test('pausing a just-started scheduled run skips collection and shows the paused state',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);
  await Promise.all([f.service.tick(),f.service.pause()]);
  assert.equal(f.counts().collects,0);assert.equal(f.service.status().enabled,false);
  assert.equal(f.service.status().status,'paused');assert.match(f.service.status().message,/暂停/);
  const saved=JSON.parse(await readFile(join(f.stateDir,'state.json'),'utf8'));
  assert.equal(saved.enabled,false);assert.equal(saved.status,'paused');
});

test('pausing while a selected draft reloads state also preserves the new schedule choice',async t=>{
  const f=await fixture(t,{draft:async report=>{await report.onSubmitting({messageId:'draft-after-pause'});return {content:'合成拍摄稿'};}});
  await f.service.saveProfile(profile);await f.service.run();const report=f.service.status().lastReport;
  await Promise.all([f.service.draft({reportId:report.id,itemId:report.items[0].id}),f.service.pause()]);
  assert.equal(f.service.status().enabled,false);assert.equal(f.service.status().status,'paused');
  const saved=JSON.parse(await readFile(join(f.stateDir,'state.json'),'utf8'));
  assert.equal(saved.enabled,false);assert.equal(saved.status,'paused');
  assert.equal(saved.drafts[report.id+':'+report.items[0].id].messageId,'draft-after-pause');
});

test('login expiry pauses attempts, publishes a rescan hint and resumes without consuming unseen content',async t=>{
  const f=await fixture(t);f.login(false);await f.service.saveProfile(profile);await f.service.tick();
  assert.equal(f.service.status().status,'login_required');assert.match(f.service.status().message,/扫码/);
  await f.service.tick();assert.deepEqual(f.counts(),{collects:0,deliveries:0});
  f.login(true);await f.service.checkLogin();await f.service.tick();assert.deepEqual(f.counts(),{collects:1,deliveries:1});
});

test('expiry during collection is not an empty success or marked seen',async t=>{
  const f=await fixture(t);let first=true;
  f.client.collect=async()=>{if(first){first=false;throw Object.assign(Error('expired'),{code:'LOGIN_REQUIRED'});}return {items:[item],warnings:[]};};
  await f.service.saveProfile(profile);await f.service.tick();assert.equal(f.service.status().status,'login_required');
  assert.equal(f.counts().deliveries,0);await f.service.checkLogin();await f.service.run();assert.equal(f.counts().deliveries,1);
});

test('paused schedules stay paused across restart; explicit manual run still works',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);await f.service.pause();
  const reopened=await createContentWatch({stateDir:f.stateDir,client:f.client,deliver:async()=>({content:'合成摘要'}),clock:f.time});
  await reopened.tick();assert.equal(f.counts().collects,0);assert.equal(reopened.status().enabled,false);
  await reopened.run();assert.equal(f.counts().collects,1);assert.equal(reopened.status().enabled,false);
});

test('sleep recovery performs one current run, never replays each missed interval',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);f.setTime(f.time()+10*INTERVAL_MS);
  f.client.collect=async()=>({items:[{...item,publishedAt:new Date(f.time()).toISOString()}]});await f.service.tick();
  assert.equal(f.counts().deliveries,1);assert.equal(f.service.status().nextRunAt,f.time()+INTERVAL_MS);
});

test('known old notes are excluded even when a collector returns them as recent search results',async t=>{
  const f=await fixture(t);f.client.collect=async()=>({items:[{...item,publishedAt:'2020-01-01T00:00:00Z'}]});
  await f.service.saveProfile(profile);await f.service.run();assert.equal(f.counts().deliveries,0);assert.equal(f.service.status().lastReport,null);
});

test('an incomplete lock gets a visible grace period then recovers instead of silently blocking forever',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);
  const path=join(f.stateDir,'run.lock');await writeFile(path,'');
  await f.service.run();assert.equal(f.counts().collects,0);assert.match(f.service.status().message,/任务锁|稍后/);
  assert.equal(await readFile(path,'utf8'),'','do not steal a just-created lock');
  const old=new Date(Date.now()-120000);await utimes(path,old,old);
  await f.service.tick();assert.equal(f.counts().collects,1);assert.equal(f.service.status().status,'ready');
  await assert.rejects(stat(path),{code:'ENOENT'});
});

test('collection failure remains visible and does not deliver invented empty results',async t=>{
  const f=await fixture(t);f.client.collect=async()=>{throw Error('temporary network failure');};
  await f.service.saveProfile(profile);await f.service.run();assert.equal(f.service.status().status,'error');
  assert.equal(f.counts().deliveries,0);assert.equal(f.service.status().lastReport,null);
});

test('persisted deduplication survives restart and preserves prior report on no new content',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);await f.service.run();const before=f.service.status().lastReport.id;
  let sent=0;const reopened=await createContentWatch({stateDir:f.stateDir,client:f.client,deliver:async()=>{sent++;},clock:f.time});
  await reopened.run();assert.equal(sent,0);assert.equal(reopened.status().lastReport.id,before);assert.match(reopened.status().message,/没有新增/);
});

test('an interrupted dispatch retains its report and does not automatically repeat a paid message',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);await f.service.run();
  const path=join(f.stateDir,'state.json'),saved=JSON.parse(await readFile(path,'utf8'));
  saved.active={id:'uncertain-run',phase:'submitting',startedAt:f.time()};await writeFile(path,JSON.stringify(saved));
  const reopened=await createContentWatch({stateDir:f.stateDir,client:f.client,deliver:async()=>{throw Error('must not resubmit');},clock:f.time});
  assert.equal(reopened.status().enabled,false);assert.ok(reopened.status().lastReport);assert.match(reopened.status().message,/中断|核对/);
  await reopened.tick();assert.equal(reopened.status().lastReport.id,saved.lastReport.id);
});

test('pending model result is kept with sources and is never blindly re-dispatched',async t=>{
  let sent=0;const f=await fixture(t,{deliver:async()=>{sent++;return {sessionId:'qx-content-watch',pending:true,content:''};}});
  await f.service.saveProfile(profile);await f.service.run();assert.match(f.service.status().lastReport.content,/企业用工常见问题/);
  assert.match(f.service.status().message,/会话/);await f.service.run();assert.equal(sent,1);
});

test('corrupt persistent state is reported instead of silently overwriting history',async t=>{
  const f=await fixture(t);await writeFile(join(f.stateDir,'state.json'),'not json');
  await assert.rejects(createContentWatch({stateDir:f.stateDir,client:f.client,deliver:async()=>{}}),/记录/);
  assert.equal(await readFile(join(f.stateDir,'state.json'),'utf8'),'not json');
});

test('two loaded instances re-read durable due state under the process lock',async t=>{
  const f=await fixture(t);await f.service.saveProfile(profile);let otherSent=0;
  const other=await createContentWatch({stateDir:f.stateDir,client:f.client,deliver:async()=>{otherSent++;return {content:'重复摘要'};},clock:f.time});
  await f.service.tick();await other.tick();assert.equal(otherSent,0);
});

test('failure before session admission leaves content available for a manual retry',async t=>{
  let attempts=0;const f=await fixture(t,{deliver:async report=>{
    attempts++;if(attempts===1)throw Error('workspace not ready');
    await report.onSubmitting({messageId:'synthetic'});return {content:'重试摘要'};
  }});
  await f.service.saveProfile(profile);await f.service.run();await f.service.run();assert.equal(attempts,2);
  assert.match(f.service.status().lastReport.content,/重试摘要/);
});

test('delivery preparation fails before collection and can be retried without consuming an API call',async t=>{
  let preparations=0;
  const f=await fixture(t,{prepareDelivery:async()=>{if(++preparations===1)throw Error('model not ready');}});
  await f.service.saveProfile(profile);await f.service.run();
  assert.equal(f.service.status().status,'error');assert.equal(f.service.status().lastReport,null);
  assert.deepEqual(f.counts(),{collects:0,deliveries:0});
  await f.service.run();assert.equal(preparations,2);assert.deepEqual(f.counts(),{collects:1,deliveries:1});
});

test('a saved unsubmitted report survives restart and retries delivery without another collection or token check',async t=>{
  const f=await fixture(t,{deliver:async()=>{throw Error('session disappeared before submission');}});
  await f.service.saveProfile(profile);await f.service.run();
  const original=f.service.status().lastReport;
  assert.equal(original.submitted,false);assert.equal(original.pending,true);assert.equal(f.counts().collects,1);
  f.client.checkLogin=async()=>{throw Error('a cached report does not need API credentials');};
  let retried,preparations=0;
  const reopened=await createContentWatch({stateDir:f.stateDir,client:f.client,clock:f.time,
    prepareDelivery:async()=>{preparations++;},deliver:async report=>{
      retried=report;await report.onSubmitting({messageId:'cached-report-message'});return {content:'缓存报告重投摘要'};
    }});
  t.after(()=>reopened.dispose());await reopened.run();
  assert.equal(preparations,1);assert.equal(f.counts().collects,1);
  assert.equal(retried.id,original.id);assert.equal(retried.createdAt,original.createdAt);
  assert.match(retried.content,/企业用工常见问题/);
  assert.equal(reopened.status().lastReport.id,original.id);assert.equal(reopened.status().lastReport.submitted,true);
  assert.match(reopened.status().lastReport.content,/缓存报告重投摘要/);
  assert.equal(reopened.status().nextRunAt,f.time()+INTERVAL_MS);
});

test('a changed lawyer profile collects afresh instead of delivering an old unsubmitted report',async t=>{
  let attempts=0,delivered;
  const f=await fixture(t,{deliver:async report=>{if(++attempts===1)throw Error('session not ready');delivered=report;await report.onSubmitting({messageId:'changed-profile'});return {content:'新方向摘要'};}});
  await f.service.saveProfile(profile);await f.service.run();const previous=f.service.status().lastReport.id;
  await f.service.saveProfile({...profile,practice:'婚姻家事',targetClients:'家庭客户'});await f.service.run();
  assert.equal(f.counts().collects,2);assert.notEqual(delivered.id,previous);
  assert.deepEqual(delivered.profile,{practice:'婚姻家事',targetClients:'家庭客户'});
  assert.equal(JSON.parse(await readFile(join(f.stateDir,'reports',previous+'.json'),'utf8')).profile.practice,profile.practice);
});

test('submission intent prevents a failed or uncertain report from being blindly delivered again',async t=>{
  let attempts=0;
  const f=await fixture(t,{deliver:async report=>{attempts++;await report.onSubmitting({messageId:'uncertain-report'});throw Error('queue outcome unknown');}});
  await f.service.saveProfile(profile);await f.service.run();const report=f.service.status().lastReport;
  assert.equal(report.submitted,true);assert.equal(report.pending,true);
  const reopened=await createContentWatch({stateDir:f.stateDir,client:f.client,clock:f.time,deliver:async()=>{attempts++;throw Error('must not redeliver');}});
  t.after(()=>reopened.dispose());await reopened.run();
  assert.equal(attempts,1);assert.equal(reopened.status().lastReport.id,report.id);
});

test('an interrupted unsubmitted report stays paused until explicitly resumed, then reuses its saved sources',async t=>{
  const f=await fixture(t,{deliver:async()=>{throw Error('not submitted');}});
  await f.service.saveProfile(profile);await f.service.run();
  const path=join(f.stateDir,'state.json'),saved=JSON.parse(await readFile(path,'utf8'));
  saved.active={id:saved.lastReport.id,phase:'preparing-session',startedAt:f.time()};await writeFile(path,JSON.stringify(saved));
  let deliveries=0;
  const reopened=await createContentWatch({stateDir:f.stateDir,client:f.client,clock:f.time,deliver:async report=>{deliveries++;await report.onSubmitting({messageId:'recovered-report'});return {content:'恢复摘要'};}});
  t.after(()=>reopened.dispose());assert.equal(reopened.status().enabled,false);
  await reopened.tick();assert.equal(deliveries,0);assert.equal(f.counts().collects,1);
  await reopened.resume();await reopened.tick();
  assert.equal(deliveries,1);assert.equal(f.counts().collects,1);assert.equal(reopened.status().lastReport.id,saved.lastReport.id);
});

test('a missing summary model blocks scheduled collection until an explicit retry or resume',async t=>{
  let ready=false,preparations=0;
  const f=await fixture(t,{prepareDelivery:async()=>{preparations++;if(!ready)throw Object.assign(Error('private provider diagnostic'),{code:'MODEL_REQUIRED'});}});
  await f.service.saveProfile(profile);await f.service.tick();await f.service.tick();
  assert.equal(f.service.status().status,'model_required');assert.match(f.service.status().message,/选择.*配置.*模型/);
  assert.doesNotMatch(f.service.status().message,/private provider/);assert.equal(preparations,1);assert.equal(f.counts().collects,0);
  ready=true;await f.service.resume();await f.service.tick();assert.equal(f.counts().collects,1);
  assert.equal(f.service.status().status,'ready');
});

test('an explicit saved-report retry never falls back to collection after the saved profile changes',async t=>{
  const f=await fixture(t,{deliver:async()=>{throw Error('not submitted');}});
  await f.service.saveProfile(profile);await f.service.run();const report=f.service.status().lastReport;
  await f.service.saveProfile({...profile,practice:'婚姻家事'});await f.service.run({retryReportId:report.id});
  assert.equal(f.counts().collects,1);assert.equal(f.service.status().status,'error');
  assert.equal(f.service.status().lastReport.id,report.id);
  assert.deepEqual(report.profile,{practice:profile.practice,targetClients:profile.targetClients});
});
