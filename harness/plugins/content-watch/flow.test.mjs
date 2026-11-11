import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {installContentWatch} from './index.mjs';
import {installKnowledge} from '../../desktop/integration/knowledge-api.mjs';
import {KnowledgeStore} from '../../desktop/integration/knowledge-store.mjs';

test('real adapter, routes, scheduler, source archive, project binding and selected draft compose without live services',async t=>{
  t.mock.method(globalThis,'fetch',async()=>{throw Error('合成测试禁止真实网络请求。');});
  const stateDir=await mkdtemp(join(tmpdir(),'qx-content-flow-')),store=new KnowledgeStore(':memory:');
  const routes=new Map(),services=new Map(),listeners=new Map(),messages=[],requests=[];
  const sessionId='qx-content-watch',token='synthetic-only-flow-token',noteId='synthetic-note',now=Math.floor(Date.now()/1000);
  const privateProject=store.project({title:'合成客户案件'});store.bind('private-chat',privateProject.id);
  store.resource(privateProject.id,{document:'private-document',title:'合成未授权原件'});
  const emit=(event,...args)=>{for(const fn of listeners.get(event)||[])fn(...args);};
  const agent={model:{current:()=>({provider:'synthetic-provider',model:'synthetic-model'})},session:{id:sessionId},whenIdle:async()=>{},followup(message){
    assert.equal(store.binding(sessionId),'lawyer-content');messages.push(message);const turn=messages.length;
    emit('agent/inbox/claimed',{agent,message,turn});
    emit('session/event',{id:sessionId},{type:'assistant/message',data:{turn,message:{content:[{type:'text',text:turn===1?'合成选题摘要':'合成口播及手机分镜'}]}}});
    emit('session/event',{id:sessionId},{type:'turn/end',data:{turn,reason:{kind:'completed'}}});
  }};
  services.set('llm',{listProviders:()=>[{id:'synthetic-provider'}]});
  services.set('workspaceRegistry',{create:async()=>({attachSession:async id=>assert.equal(id,sessionId)})});
  const ctx={provide:(name,value)=>services.set(name,value),get:name=>services.get(name),agents:{get:()=>agent},
    connection:{fetch:{register:route=>routes.set(route.path,route)}},systemPrompt:{context:()=>()=>{}},tools:{register(){}},effect:fn=>fn(),
    on(event,fn){if(!listeners.has(event))listeners.set(event,new Set());listeners.get(event).add(fn);return()=>listeners.get(event).delete(fn);},
    loader:{internal:{import:async name=>{assert.equal(name,'@deepseek-ai/dsh-llm');return {createUserMessage:input=>({id:randomUUID(),...input})};}}}};
  const knowledge=installKnowledge(ctx,{store,schedule:false,source:{list:async()=>[],describe:async()=>({records:[]}),current:async()=>'v1'},model:async()=>({items:[]})});
  const note={id:noteId,title:'合成劳动争议选题',desc:'合成正文：讨论用工变更中的沟通问题。',type:'normal',user:{nickname:'合成作者'},liked_count:'88',comments_count:'9',collected_count:'12',shared_count:'1',timestamp:now,time:now};
  const watcher=await installContentWatch(ctx,{stateDir,workspace:join(stateDir,'workspace')},{schedule:false,fetchImpl:async(url,options)=>{
    const u=new URL(url);assert.equal(u.origin,'https://api.justoneapi.com');assert.equal(u.searchParams.get('token'),token);assert.equal(options.redirect,'error');requests.push(u.pathname);
    if(u.pathname.endsWith('/search-note/v4'))return Response.json({code:0,data:{notes:[note]}});
    assert.equal(u.pathname,'/api/xiaohongshu/get-note-detail/v1');return Response.json({code:0,data:[{model_type:'note',note_list:[note]}]});
  }});
  t.after(async()=>{await watcher.dispose();knowledge.dispose();await rm(stateDir,{recursive:true,force:true});});
  const call=async(path,data)=>{
    const req=new Request('http://dsh.internal/api/qx-content-watch/'+path,{method:data?'POST':'GET',headers:{host:'127.0.0.1:9999','x-qx-content-watch':'1',...(data?{'content-type':'application/json'}:{})},...(data?{body:JSON.stringify(data)}:{})});
    const response=await routes.get('/api/qx-content-watch/'+path).fetch(req);assert.ok(response.ok);return response.json();
  };
  await call('connection',{provider:'justone',token});await call('action',{action:'check-login'});assert.equal(requests.length,0);
  await call('profile',{practice:'劳动争议',targetClients:'企业负责人',enabled:true});await call('action',{action:'run'});await watcher.whenIdle();
  const state=await call('status');assert.equal(state.status,'ready');assert.equal(state.lastReport.items[0].id,noteId);assert.match(state.lastReport.content,/合成选题摘要/);
  assert.equal(requests.length,5);assert.equal(messages.length,1);assert.equal(messages[0].source.kind,'qx-content-watch');
  assert.match(messages[0].content[0].text,/合成正文/);assert.ok(!JSON.stringify(messages).includes(token));
  const report=JSON.parse(await readFile(join(stateDir,'reports',state.lastReport.id+'.json'),'utf8'));
  assert.equal(report.items[0].likes,88);assert.equal(report.items[0].textCoverage,'正文');
  await call('action',{action:'draft',reportId:report.id,itemId:noteId});await watcher.whenIdle();
  assert.equal(messages.length,2);assert.match(messages[1].content[0].text,/60–90 秒|60–90秒/);assert.match(messages[1].content[0].text,/legal_search/);
  await call('action',{action:'draft',reportId:report.id,itemId:noteId});await watcher.whenIdle();assert.equal(messages.length,2);
  assert.equal(store.binding('private-chat'),privateProject.id);assert.equal(store.resources(privateProject.id).length,1);assert.equal(store.resources('lawyer-content').length,0);
  assert.ok(!JSON.stringify(await call('status')).includes(token));
});
