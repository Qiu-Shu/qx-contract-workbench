import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {installContentWatch} from './index.mjs';

async function fixture(t){
  const stateDir=await mkdtemp(join(tmpdir(),'qx-watch-route-')),routes=new Map(),effects=[];
  const calls={start:0,prepare:0,collect:0,deliver:0,draft:0,preflight:0};
  const ctx={connection:{fetch:{register:r=>routes.set(r.path,r)}},effect:fn=>effects.push(fn())};
  const item={id:'synthetic-note',title:'合成劳动争议选题',url:'https://www.xiaohongshu.com/explore/synthetic-note',text:'合成资料',textCoverage:'正文'};
  const watcher=await installContentWatch(ctx,{stateDir,workspace:join(stateDir,'workspace')},{schedule:false,
    client:{checkLogin:async()=>({loggedIn:true,verified:false}),collect:async()=>{calls.collect++;return {items:[item]};}},
    runtime:{ensureStarted:async()=>{calls.start++;},stop:async()=>{}},prepareComponent:async()=>{calls.prepare++;},
    sessionDelivery:{prepare:async()=>{calls.preflight++;},deliver:async report=>{calls.deliver++;await report.onSubmitting({messageId:'report-message'});return {content:'合成摘要'};},
      draft:async report=>{calls.draft++;await report.onSubmitting({messageId:'draft-message'});return {content:'合成口播与拍摄稿'};},dispose(){}}});
  t.after(async()=>{await watcher.dispose();await rm(stateDir,{recursive:true,force:true});});
  async function request(path,data,headers={}){
    const request=new Request('http://dsh.internal/api/qx-content-watch/'+path,{method:data===undefined?'GET':'POST',
      headers:{host:'127.0.0.1:9999','x-qx-content-watch':'1','content-type':'application/json',...headers},...(data===undefined?{}:{body:typeof data==='string'?data:JSON.stringify(data)})});
    const response=await routes.get('/api/qx-content-watch/'+path).fetch(request);return {status:response.status,value:await response.json()};
  }
  return {stateDir,watcher,request,calls,routes};
}
test('registration stays idle; rejects cross-site and malformed writes without echoing credentials',async t=>{
  const f=await fixture(t);assert.equal(f.calls.collect,0);
  assert.equal((await f.request('status')).value.connection.provider,'justone');
  assert.equal((await f.request('connection',{provider:'justone',token:'synthetic-secret'},{origin:'https://unrelated.invalid'})).status,403);
  assert.equal((await f.request('connection','{"token":"synthetic-secret"')).status,400);
  assert.equal((await f.request('connection','x'.repeat(17000))).status,413);
  const assets=await f.routes.get('/api/qx-content-watch/client.js').fetch(new Request('http://dsh.internal/api/qx-content-watch/client.js'));
  assert.match(assets.headers.get('content-type'),/javascript/);
});
test('profile, API credential, collection, source report and selected draft form one synthetic flow',async t=>{
  const f=await fixture(t);
  const saved=await f.request('connection',{provider:'justone',token:'synthetic-secret'});
  assert.equal(saved.status,200);assert.equal(saved.value.connection.tokenConfigured,true);assert.doesNotMatch(JSON.stringify(saved.value),/synthetic-secret/);
  await f.request('profile',{practice:'劳动用工',targetClients:'企业负责人',enabled:true});
  assert.equal((await f.request('action',{action:'run'})).status,202);await f.watcher.whenIdle();
  let state=(await f.request('status')).value;assert.match(state.lastReport.content,/合成摘要/);assert.equal(state.lastReport.items.length,1);
  assert.equal(f.calls.start,0);assert.equal(f.calls.prepare,0);assert.equal(f.calls.deliver,1);assert.equal(f.calls.preflight,1);
  const selection={action:'draft',reportId:state.lastReport.id,itemId:state.lastReport.items[0].id};
  await f.request('action',selection);await f.watcher.whenIdle();await f.request('action',selection);await f.watcher.whenIdle();
  assert.equal(f.calls.draft,1);assert.doesNotMatch(await readFile(join(f.stateDir,'state.json'),'utf8'),/synthetic-secret/);
  assert.equal((await f.request('action',{action:'login'})).status,400,'API never starts QR flow');
  await f.request('connection',{provider:'local-xhs'});await f.request('action',{action:'prepare'});await f.watcher.whenIdle();
  assert.equal(f.calls.prepare,1);assert.ok(f.calls.start>0);
});
test('task start rejects missing profile and unrecognized selections before accepting background work',async t=>{
  const f=await fixture(t);
  assert.equal((await f.request('action',{action:'run'})).status,400);
  assert.equal((await f.request('action',{action:'draft',reportId:'../private',itemId:'x'})).status,400);
  assert.equal((await f.request('action',{action:'unknown'})).status,400);
  assert.equal(f.calls.collect,0);assert.equal(f.calls.draft,0);
});
test('cached retry route validates its id and never falls back to paid collection',async t=>{
  const f=await fixture(t);
  await f.request('profile',{practice:'劳动争议',targetClients:'企业负责人',enabled:true});
  for(const retryReportId of ['',42,'x'.repeat(129)])assert.equal((await f.request('action',{action:'run',retryReportId})).status,400);
  assert.equal((await f.request('action',{action:'run',retryReportId:'stale-report'})).status,202);
  await f.watcher.whenIdle();
  assert.equal((await f.request('status')).value.status,'error');
  assert.equal(f.calls.collect,0);assert.equal(f.calls.preflight,0);assert.equal(f.calls.deliver,0);
});
