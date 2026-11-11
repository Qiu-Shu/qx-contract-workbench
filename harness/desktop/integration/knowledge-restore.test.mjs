import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {KnowledgeStore} from './knowledge-store.mjs';
import {KnowledgeRunner} from './knowledge-runtime.mjs';
import {installKnowledge} from './knowledge-api.mjs';
import {fixture as application} from '../../tests/helpers.mjs';

const item={kind:'summary',title:'合成付款事项',content:'合成甲方应核对付款条件',sources:[{seq:1,quote:'核对付款条件'}]};
function fixture(t,count=1){
  const s=new KnowledgeStore(':memory:');t.after(()=>s.close());
  s.project({id:'a',title:'合成案件A'});s.bind('chat','a');s.source('chat','v1');
  for(let i=0;i<count;i++)s.upsertBatch('chat','v1','batch-'+i,[item]);
  const e=s.list('a')[0];s.review(e.id,{action:'edit',revision:e.revision,content:'合成甲方补充付款条件'});
  return s;
}
function target(t,path=':memory:'){const s=new KnowledgeStore(path);t.after(()=>s.close());return s;}
const absent={list:async()=>[],current:async()=>null};
function pages(s){const result=[];let offset=0;do{const part=s.exportPage(offset);result.push(part);offset=part.next;}while(offset!==null);return result;}

for(const method of ['reconcile','fresh','syncProjectMaterials'])test('新设备恢复后 '+method+' 保留正文、引用与历史',async t=>{
  const original=fixture(t),s=target(t),backup=original.exportPage();s.restore(backup);
  const before=s.list('a')[0],history=s.history(before.id,'a');
  const runner=new KnowledgeRunner({store:s,source:absent});await runner[method](method==='fresh'?'chat':'a');
  const after=s.entry(before.id,'a');assert.equal(after.content,'合成甲方补充付款条件');assert.deepEqual(after.sources,before.sources);
  assert.equal(after.state,'pending');assert.equal(after.sourceStatus,'unavailable');assert.deepEqual(s.history(before.id,'a'),history);
  assert.equal(s.origins()[0].deleted,0);assert.equal(s.search('a','付款').length,0);
});

test('恢复后真实API刷新、列表、历史、导出及重启再恢复不丢资料',async t=>{
  const root=mkdtempSync(join(tmpdir(),'qx-restore-'));t.after(()=>rmSync(root,{recursive:true,force:true}));
  const original=fixture(t),path=join(root,'knowledge.sqlite'),s=new KnowledgeStore(path),routes=new Map();
  const ctx={connection:{fetch:{register:r=>routes.set(r.path,r)}},effect:()=>{},systemPrompt:{context:()=>{}},tools:{register:()=>{}}};
  const handle=installKnowledge(ctx,{store:s,source:absent,schedule:false,caseMemory:async()=>({items:[]})});
  const get=async name=>{const response=await routes.get('/api/qx-layered/'+name.split('?')[0]).fetch(new Request('http://localhost/api/qx-layered/'+name,{headers:{'x-qx-layered':'1'}}));assert.equal(response.status,200);return response.json();};
  s.restore(original.exportPage());const id=s.list('a')[0].id;
  try{await get('state');const listed=await get('list?project=a');assert.equal(listed.items[0].sourceStatus,'unavailable');assert.equal(listed.items[0].content,'合成甲方补充付款条件');assert.equal((await get('history?project=a&entryId='+id)).items[0].content,item.content);await get('backup');}finally{handle.dispose();}
  const reopened=new KnowledgeStore(path);
  try{await new KnowledgeRunner({store:reopened,source:absent}).reconcile();const again=target(t);again.restore(reopened.exportPage());await new KnowledgeRunner({store:again,source:absent}).fresh('chat');assert.equal(again.entry(id,'a').content,'合成甲方补充付款条件');assert.equal(again.history(id,'a')[0].content,item.content);}finally{reopened.close();}
});

test('明确删除仍清空历史且旧备份不能复活，删除标记可迁入空设备',async t=>{
  const original=fixture(t),backup=original.exportPage(),s=target(t);s.restore(backup);s.invalidate('chat',true);s.restore(backup);
  assert.ok(s.list('a').every(e=>e.content===''));assert.ok(s.history(backup.entries[0].id,'a').every(e=>e.content===''));
  const fresh=target(t);fresh.restore(s.exportPage());fresh.restore(backup);assert.equal(fresh.list('a').length,0);assert.equal(fresh.origins()[0].deleted,1);
});

test('迁入来源核对成功后沿用本机删除规则',async t=>{
  const original=fixture(t),s=target(t);s.restore(original.exportPage());let exists=true;
  const source={list:async()=>exists?[{id:'chat'}]:[],current:async()=>exists?'v1':null};
  const runner=new KnowledgeRunner({store:s,source});assert.equal(await runner.fresh('chat'),true);assert.equal(s.list('a')[0].sourceStatus,'available');
  exists=false;await runner.reconcile();assert.equal(s.list('a')[0].content,'');assert.equal(s.origins()[0].deleted,1);
});

test('界面同步见到迁入会话后即记录本机存在，随后删除仍清理',async t=>{
  const original=fixture(t),s=target(t);s.restore(original.exportPage());let exists=true;
  const source={list:async()=>exists?[{id:'chat'}]:[],current:async()=>exists?'v1':null};
  const runner=new KnowledgeRunner({store:s,source});await runner.reconcile();exists=false;await runner.reconcile();
  assert.equal(s.list('a')[0].content,'');assert.equal(s.origins()[0].deleted,1);
});

test('旧备份按当前B归属恢复摘要与历史，A不可读且返回冲突记录',t=>{
  const original=fixture(t),s=target(t);s.project({id:'b',title:'B'});s.bind('chat','b');s.source('chat','v1');
  const result=s.restore(original.exportPage());assert.equal(result.conflicts,1);assert.equal(s.binding('chat'),'b');assert.equal(s.list('a').length,0);
  const e=s.list('b')[0];assert.equal(e.state,'pending');assert.ok(s.history(e.id,'b').every(r=>r.project==='b'));assert.throws(()=>s.entry(e.id,'a'));
  s.review(e.id,{action:'confirm',revision:e.revision,project:'b'});assert.equal(s.search('a','付款').length,0);assert.equal(s.search('b','付款').length,1);assert.equal(JSON.parse(s.context('a','付款')).summaries.length,0);
  assert.ok(s.db.prepare('SELECT action FROM audit WHERE entry=?').all(e.id).some(r=>r.action.includes('restore-scope-conflict')));
});

test('重复导入不覆盖B现有人工更正，旧备份历史归属仍一致',t=>{
  const original=fixture(t),s=target(t),backup=original.exportPage();s.restore(backup);s.project({id:'b',title:'B'});s.bind('chat','b');
  let e=s.list('b')[0];e=s.review(e.id,{action:'edit',revision:e.revision,content:'B的人工更正'});const revision=e.revision;
  s.restore(backup);s.restore(backup);assert.equal(s.entry(e.id,'b').content,'B的人工更正');assert.equal(s.entry(e.id,'b').revision,revision);assert.equal(s.list('a').length,0);
  assert.ok(s.history(e.id,'b').every(r=>r.project==='b'));
});

test('多页逆序和重复导入保持当前归属且条目不丢失',async t=>{
  const original=fixture(t,56),s=target(t);s.project({id:'b',title:'B'});s.bind('chat','b');s.source('chat','v1');
  const all=pages(original).reverse();for(const p of [...all,...all])s.restore(p);
  assert.equal(s.db.prepare('SELECT COUNT(*) n FROM entries WHERE project=?').get('b').n,56);assert.equal(s.list('a').length,0);
  assert.equal(s.db.prepare("SELECT COUNT(*) n FROM revisions WHERE project!='b'").get().n,0);
});

test('来源版本不同不恢复旧摘要，损坏批次整体回滚且可重试',t=>{
  const original=fixture(t),backup=original.exportPage(),s=target(t);s.project({id:'b',title:'B'});s.bind('chat','b');s.source('chat','v2');assert.equal(s.restore(backup).imported,0);
  const fresh=target(t),bad=structuredClone(backup);bad.entries.push({...bad.entries[0],id:'broken',sources:'not-json'});
  assert.throws(()=>fresh.restore(bad));assert.equal(fresh.origins().length,0);assert.equal(fresh.db.prepare('SELECT COUNT(*) n FROM entries').get().n,0);
  fresh.restore(backup);assert.equal(fresh.list('a')[0].content,'合成甲方补充付款条件');
});

test('恢复修正此前错配条目的归属，保留内容并撤销跨案共享',t=>{
  const original=fixture(t),s=target(t),backup=original.exportPage();s.restore(backup);s.project({id:'b',title:'B'});
  s.db.prepare('UPDATE bindings SET project=? WHERE session=?').run('b','chat');s.db.prepare('UPDATE entries SET shared=1').run();
  s.restore(backup);assert.equal(s.list('a').length,0);assert.equal(s.list('b')[0].content,'合成甲方补充付款条件');assert.equal(s.list('b')[0].shared,0);
  assert.ok(s.history(s.list('b')[0].id,'b').every(r=>r.project==='b'));
});

test('当前B的摘要不能通过A的HTTP入口或模型召回读取',async t=>{
  const original=fixture(t),f=application();t.after(()=>f.service.dispose());
  f.add('chat','B会话',[{seq:1,role:'user',text:'合成甲方应核对付款条件'}]);
  const version=await f.source.current('chat');original.source('chat',version,{preserve:true});
  f.store.project({id:'b',title:'B'});f.store.bind('chat','b');f.store.source('chat',version);f.store.restore(original.exportPage());
  const e=f.store.list('b')[0];f.store.review(e.id,{action:'confirm',revision:e.revision,project:'b'});
  f.add('other','A会话',[{seq:1,role:'user',text:'独立虚构交通事项'}]);f.store.bind('other','a');
  const list=await(await f.request('list?project=a')).json();assert.equal(list.items.length,0);
  assert.equal((await f.request('entry?project=a&entryId='+e.id)).status,404);
  assert.equal((await f.request('history?project=a&entryId='+e.id)).status,404);
  assert.equal((await f.request('trace',{project:'a',entryId:e.id,seq:1})).status,404);
  assert.ok(!JSON.stringify(await f.call('knowledge_start',{query:'合成甲方'},'other')).includes('合成甲方补充付款条件'));
  assert.equal((await f.call('knowledge_recall',{query:'合成甲方'},'other')).length,0);
  assert.ok((await f.call('knowledge_read',{entryId:e.id},'other')).error);
  assert.ok((await f.call('knowledge_recall',{query:'合成甲方'},'chat')).some(r=>r.id===e.id));
});

test('旧版待归属备份没有绑定记录仍可恢复，当前绑定仍优先',t=>{
  const legacy=target(t);legacy.source('legacy-chat','v1');legacy.upsertBatch('legacy-chat','v1','batch',[item]);const backup=legacy.exportPage();assert.equal(backup.bindings.length,0);
  const fresh=target(t);fresh.restore(backup);assert.equal(fresh.list('inbox')[0].content,item.content);assert.equal(fresh.list('inbox')[0].sourceStatus,'unavailable');
  const current=target(t);current.project({id:'b',title:'B'});current.bind('legacy-chat','b');current.source('legacy-chat','v1');current.restore(backup);
  assert.equal(current.list('inbox').length,0);assert.equal(current.list('b')[0].content,item.content);
});

test('移项后仅含历史的靠后分页可独立恢复且逆序导入完整',t=>{
  const original=fixture(t);for(let i=0;i<30;i++)original.project({id:'extra-'+i,title:'合成项目'+i});original.project({id:'b',title:'B'});
  original.bind('chat','b');let e=original.list('b')[0];for(let i=0;i<55;i++)e=original.review(e.id,{action:'edit',revision:e.revision,content:'合成修订'+i});
  // Exercise a history-only page whose original scope A differs from current scope B.
  original.db.prepare("UPDATE revisions SET project='a' WHERE entry=?").run(e.id);
  const parts=pages(original),restored=target(t);for(const part of parts.toReversed())restored.restore(part);
  assert.equal(restored.entry(e.id,'b').content,'合成修订54');
  assert.equal(restored.db.prepare('SELECT COUNT(*) n FROM revisions WHERE entry=?').get(e.id).n,original.db.prepare('SELECT COUNT(*) n FROM revisions WHERE entry=?').get(e.id).n);
  assert.equal(restored.db.prepare("SELECT COUNT(*) n FROM revisions WHERE project!='b'").get().n,0);
});

test('人工确认的迁入规则可读取保存正文，模型仍知原文未迁入且不能伪装追溯',async t=>{
  const original=fixture(t);original.upsertBatch('chat','v1','rule',[{...item,kind:'rule',title:'合成付款规则',content:'合成规则正文'.repeat(120)}]);
  const f=application();t.after(()=>f.service.dispose());f.store.restore(original.exportPage());
  const e=f.store.list('a').find(r=>r.kind==='rule');f.store.review(e.id,{action:'confirm',revision:e.revision,project:'a'});
  f.add('viewer','查看迁入规则',[{seq:1,role:'user',text:'请读取合成付款规则'}]);f.store.bind('viewer','a');
  const start=await f.call('knowledge_start',{query:'合成付款规则'},'viewer');const index=JSON.parse(start.memory).layer1.find(r=>r.id===e.id);
  assert.equal(index.sourceStatus,'unavailable');
  const body=await f.call('knowledge_read',{entryId:e.id},'viewer');assert.ok(!body.error);assert.ok(body.content.startsWith('合成规则正文'));assert.equal(body.sourceStatus,'unavailable');
  const trace=await f.call('knowledge_read',{entryId:e.id,source:true},'viewer');assert.ok(trace.error);assert.equal(trace.snippets,undefined);
  assert.equal(f.store.entry(e.id,'a').content,'合成规则正文'.repeat(120));
});
