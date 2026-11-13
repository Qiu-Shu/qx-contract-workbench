import test from 'node:test';import assert from 'node:assert/strict';import {KnowledgeStore} from './knowledge-store.mjs';import {installKnowledge} from './knowledge-api.mjs';
function fixture(options={}){const routes=new Map(),tools=new Map(),services=new Map(),hooks=new Map(),effects=[],s=new KnowledgeStore(':memory:');const ctx={on:(name,handler)=>hooks.set(name,handler),provide:(name,value)=>services.set(name,value),connection:{fetch:{register:r=>routes.set(r.path,r)}},systemPrompt:{context:r=>{ctx.prompt=r;return()=>{};}},tools:{register:r=>tools.set(r.name,r)},effect:f=>{effects.push(f());},sessions:{get:()=>({id:'chat'})}};const source={list:async()=>[{id:'chat'},...s.origins().filter(row=>!row.deleted&&row.session!=='chat').map(row=>({id:row.session}))],describe:async()=>({version:'v1',records:[]}),current:async()=>'v1',read:async()=>({text:'有限原文'}),messages:async function*(){}};s.setting('settings',{enabled:false});const handle=installKnowledge(ctx,{store:s,source,model:async()=>({items:[]}),schedule:false,...options});return {ctx,s,routes,tools,services,hooks,source,runner:handle.runner,close:()=>{for(const d of effects)d?.();handle.dispose();}};}
test('界面修改必须是同源可信提交，模型检索不能自选项目',async()=>{const f=fixture();const route=f.routes.get('/api/qx-layered/project');let r=await route.fetch(new Request('http://localhost/api/qx-layered/project',{method:'POST',body:'{}'}));assert.equal(r.status,403);r=await route.fetch(new Request('http://localhost/api/qx-layered/project',{method:'POST',headers:{'x-qx-layered':'1','content-type':'application/json'},body:JSON.stringify({title:'项目'})}));assert.equal(r.status,200);const search=f.tools.get('knowledge_recall');assert.ok(!search.parameters.project);f.close();});
test('未命中来源不能直接通过模型读原文；普通对话自动取得独立项目',async()=>{const f=fixture();const result=await f.tools.get('knowledge_read').execute({entryId:'unknown'}, {agent:{session:{id:'chat'}}});assert.match(result,/未绑定项目|先检索/);const c=await f.ctx.prompt.text({agent:{session:{id:'chat'}}});assert.match(c,/当前项目索引/);assert.ok(f.s.binding('chat').startsWith('task-'));f.close();});
test('追溯入口只允许指定条目的来源，拒绝伪造seq',async()=>{const f=fixture(),p=f.s.project({title:'项目'});f.s.bind('chat',p.id);f.s.source('chat','v1');f.s.upsertBatch('chat','v1','b',[{kind:'summary',title:'摘要',content:'内容',sources:[{seq:1,quote:'原文'}]}]);const e=f.s.list(p.id)[0];const request=new Request('http://localhost/api/qx-layered/trace',{method:'POST',headers:{'x-qx-layered':'1','content-type':'application/json'},body:JSON.stringify({project:p.id,entryId:e.id,seq:99})});const r=await f.routes.get('/api/qx-layered/trace').fetch(request);assert.equal(r.status,403);f.close();});
test('Harness动态上下文必须同步返回字符串，初始化读取由受限工具完成',()=>{const f=fixture();const p=f.s.project({title:'项目'});f.s.bind('chat',p.id);const value=f.ctx.prompt.text({agent:{session:{id:'chat'}}});assert.equal(typeof value,'string');assert.match(value,/knowledge_start/);assert.ok(f.tools.has('knowledge_start'));f.close();});
test('Harness内部重写URL后仍按原Host校验同源',async()=>{const f=fixture();const route=f.routes.get('/api/qx-layered/project');const req=origin=>new Request('http://dsh.internal/api/qx-layered/project',{method:'POST',headers:{host:'127.0.0.1:3080',origin,'x-qx-layered':'1','content-type':'application/json'},body:JSON.stringify({title:'项目'})});assert.equal((await route.fetch(req('http://127.0.0.1:3080'))).status,200);assert.equal((await route.fetch(req('http://dsh.internal'))).status,403);f.close();});
test('来源移项重新整理后旧项目仍不能追溯',async()=>{const f=fixture(),p=f.s.project({title:'旧项目'}),q=f.s.project({title:'新项目'});f.s.bind('chat',p.id);f.s.source('chat','v1');f.s.upsertBatch('chat','v1','b',[{kind:'summary',title:'摘要',content:'内容',sources:[{seq:1,quote:'原文'}]}]);const e=f.s.list(p.id)[0];f.s.bind('chat',q.id);f.s.source('chat','v1');const r=await f.routes.get('/api/qx-layered/trace').fetch(new Request('http://localhost/api/qx-layered/trace',{method:'POST',headers:{'x-qx-layered':'1','content-type':'application/json'},body:JSON.stringify({project:p.id,entryId:e.id,seq:1})}));assert.equal(r.status,404);f.close();});
test('同轮检索后撤销全局授权，后续读取立即拒绝',async()=>{const f=fixture(),p=f.s.project({title:'源项目'}),q=f.s.project({title:'任务项目'});f.s.bind('chat',q.id);f.s.source('source','v1');f.s.bind('source',p.id);f.s.source('source','v1');f.s.upsertBatch('source','v1','b',[{kind:'rule',title:'付款原则',content:'核对付款条件',sources:[{seq:1,quote:'原文'}]}]);let r=f.s.list(p.id)[0];r=f.s.review(r.id,{action:'global',revision:r.revision,shared:true});const exec={agent:{session:{id:'chat'}}};await f.tools.get('knowledge_recall').execute({query:'付款'},exec);f.s.review(r.id,{action:'global',revision:r.revision,shared:false});assert.match(await f.tools.get('knowledge_read').execute({entryId:r.id},exec),/不在可读取范围/);f.close();});
test('读取过程中移项必须丢弃原文且不能授予追溯权限',async()=>{const f=fixture(),p=f.s.project({title:'旧'}),q=f.s.project({title:'新'});f.s.bind('chat',p.id);f.s.source('chat','v1');f.s.upsertBatch('chat','v1','b',[{kind:'summary',title:'摘要',content:'内容',sources:[{seq:1,quote:'原文'}]}]);const e=f.s.list(p.id)[0];f.source.read=async()=>{f.s.bind('chat',q.id);f.s.source('chat','v1');return {text:'不应返回'};};const response=await f.routes.get('/api/qx-layered/trace').fetch(new Request('http://localhost/api/qx-layered/trace',{method:'POST',headers:{'x-qx-layered':'1','content-type':'application/json'},body:JSON.stringify({project:p.id,entryId:e.id,seq:1,grantSession:'chat'})}));assert.equal(response.status,404);assert.ok(!(await response.text()).includes('不应返回'));f.close();});

test('内容服务复用已有知识库且仅绑定固定专用会话，不改写其他项目或原资料索引',()=>{
  const f=fixture(),privateProject=f.s.project({title:'客户项目',description:'律师手工说明'});
  f.s.bind('private-session',privateProject.id);f.s.resource(privateProject.id,{document:'private-document',title:'客户原件'});
  const service=f.services.get('qxKnowledge');assert.equal(typeof service.ensureContentProject,'function');
  assert.throws(()=>service.ensureContentProject('private-session'),/专用会话/);
  const binding=service.ensureContentProject('qx-content-watch');assert.equal(binding.session,'qx-content-watch');assert.equal(binding.project,'lawyer-content');
  assert.equal(f.s.getProject('lawyer-content').title,'律师内容运营');
  f.s.project({id:'lawyer-content',title:'律师内容运营',description:'已编辑的内容说明'});
  service.ensureContentProject('qx-content-watch');
  assert.equal(f.s.projects().filter(p=>p.id==='lawyer-content').length,1);
  assert.equal(f.s.getProject('lawyer-content').description,'已编辑的内容说明');
  assert.equal(f.s.binding('private-session'),privateProject.id);
  assert.deepEqual(f.s.getProject(privateProject.id),privateProject);assert.equal(f.s.resources(privateProject.id)[0].document,'private-document');
  f.close();assert.throws(()=>service.ensureContentProject('qx-content-watch'),/已停止/);
});

test('内容会话知识上下文只回读本项目已确认偏好，不携入跨项目经验、原件或外部摘要',async()=>{
  const f=fixture();f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');
  const privateProject=f.s.project({title:'私有案件'});f.s.bind('private-session',privateProject.id);f.s.source('private-session','v1');
  f.s.upsertBatch('private-session','v1','private',[{kind:'rule',title:'表达私有原则',content:'不应泄漏的案件观点',sources:[{seq:1,quote:'客户原文'}]}]);
  let other=f.s.list(privateProject.id)[0];other=f.s.review(other.id,{action:'global',revision:other.revision,shared:true});
  f.s.upsertBatch('private-session','v1','more-private',Array.from({length:10},(_,index)=>({kind:'rule',title:'表达偏好表达短句 '+index,content:'表达使用短句的跨项目私有原则',sources:[{seq:1,quote:'客户原文'}]})));
  for(const row of f.s.list(privateProject.id).filter(e=>e.state==='pending'))f.s.review(row.id,{action:'global',revision:row.revision,shared:true});
  f.s.source('qx-content-watch','v1');f.s.upsertBatch('qx-content-watch','v1','content',[
    {kind:'preference',title:'表达偏好',content:'表达使用短句',sources:[{seq:1,quote:'短句'}]},
    {kind:'summary',title:'表达外部观点',content:'不应当成偏好的外部摘要',sources:[{seq:2,quote:'帖子'}]},
    {kind:'rule',title:'表达候选',content:'未确认的候选原则',sources:[{seq:3,quote:'候选'}]},
  ]);
  let own=f.s.list('lawyer-content').find(e=>e.kind==='preference');own=f.s.review(own.id,{action:'confirm',revision:own.revision});
  f.s.resource('lawyer-content',{document:'linked-document',title:'不应自动加载的关联原件'});
  const exec={agent:{session:{id:'qx-content-watch'}}},context=f.ctx.prompt.text(exec);
  assert.match(context,/专用会话/);assert.match(context,/不要求调用知识工具/);
  assert.ok(!f.s.search('lawyer-content','表达 短句',8,{history:true}).some(e=>e.id===own.id));
  const start=await f.tools.get('knowledge_start').execute({query:'表达 短句'},exec);
  const started=JSON.parse(JSON.parse(start).memory);assert.deepEqual(started.layer1.map(e=>e.id),[own.id]);assert.equal(started.layer2.length,0);assert.ok(!start.includes('表达使用短句'));assert.match(await f.tools.get('knowledge_read').execute({entryId:own.id},exec),/表达使用短句/);
  for(const absent of ['不应泄漏','不应当成偏好','未确认的候选','不应自动加载'])assert.ok(!start.includes(absent),absent);
  const found=JSON.parse(await f.tools.get('knowledge_recall').execute({query:'表达 短句'},exec));assert.deepEqual(found.map(e=>e.id),[own.id]);
  assert.match(await f.tools.get('knowledge_read').execute({entryId:other.id},exec),/先检索/);
  assert.match(await f.tools.get('knowledge_read').execute({entryId:own.id,source:true},exec),/仅可读取本项目已确认/);
  f.close();
});

test('绑定接口拒绝把内容专用会话移到客户项目，普通会话仍可正常绑定',async()=>{
  const f=fixture();try{
    f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');
    const p=f.s.project({title:'客户项目'});f.source.list=async()=>[{id:'chat'},{id:'qx-content-watch'}];
    const bind=(session,project)=>f.routes.get('/api/qx-layered/bind').fetch(new Request('http://localhost/api/qx-layered/bind',{method:'POST',headers:{'x-qx-layered':'1','content-type':'application/json'},body:JSON.stringify({session,project,expectedProject:f.s.bindingInfo(session).project,revision:f.s.bindingInfo(session).revision})}));
    const rejected=await bind('qx-content-watch',p.id);assert.equal(rejected.status,403);assert.match(await rejected.text(),/专用会话/);
    assert.equal(f.s.binding('qx-content-watch'),'lawyer-content');
    assert.equal((await bind('qx-content-watch','lawyer-content')).status,200);
    assert.equal((await bind('chat',p.id)).status,200);assert.equal(f.s.binding('chat'),p.id);
  }finally{f.close();}
});

test('底层恢复或直接改错绑定时内容会话停止知识读取，不暴露客户项目索引',async()=>{
  const f=fixture();try{
    f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');
    const p=f.s.project({title:'绝不能带入内容会话的客户项目',description:'客户保密项目说明'});
    f.s.bind('private-session',p.id);f.s.source('private-session','v1');
    f.s.upsertBatch('private-session','v1','private-summary',[{kind:'summary',title:'付款争议',content:'绝不能带入内容会话的客户正文',sources:[{seq:1,quote:'客户原文'}]}]);
    const entry=f.s.list(p.id)[0];f.s.bind('qx-content-watch',p.id);
    let described=0;f.source.describe=async()=>{described++;return {version:'v1',records:[]};};
    const exec={agent:{session:{id:'qx-content-watch'}}},context=f.ctx.prompt.text(exec);
    assert.match(context,/绑定异常/);assert.ok(!context.includes(p.id));assert.ok(!context.includes(p.title));assert.ok(!context.includes(p.description));
    for(const [name,args] of [['knowledge_start',{query:'付款'}],['knowledge_recall',{query:'付款'}],['knowledge_read',{entryId:entry.id}]]){
      const result=await f.tools.get(name).execute(args,exec);assert.match(result,/绑定异常/);assert.ok(!result.includes(entry.content));
    }
    assert.equal(described,0);
    f.s.bind('chat',p.id);const normal=await f.tools.get('knowledge_recall').execute({query:'付款'},{agent:{session:{id:'chat'}}});assert.match(normal,/客户正文/);
    f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');assert.equal(f.s.binding('qx-content-watch'),'lawyer-content');
    assert.match(f.ctx.prompt.text(exec),/律师内容运营/);
  }finally{f.close();}
});


test('内容固定项目不可撤销，普通会话归属仍可撤销',async()=>{
  const f=fixture();try{
    f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');f.source.list=async()=>[{id:'chat'},{id:'qx-content-watch'}];
    const undo=session=>f.routes.get('/api/qx-layered/undo-bind').fetch(new Request('http://localhost/api/qx-layered/undo-bind',{method:'POST',headers:{'x-qx-layered':'1','content-type':'application/json'},body:JSON.stringify({session,revision:f.s.bindingInfo(session).revision})}));
    assert.equal((await undo('qx-content-watch')).status,403);assert.equal(f.s.binding('qx-content-watch'),'lawyer-content');
    const p=f.s.project({title:'普通项目'});f.s.bind('chat',p.id);assert.equal((await undo('chat')).status,200);assert.equal(f.s.binding('chat'),'inbox');
  }finally{f.close();}
});

test('内容工具不读取附件或案件记忆，直接私有资料结果不会进入模型上下文',async()=>{
  let caseReads=0;const f=fixture({caseMemory:async()=>{caseReads++;return {items:[]};}});try{
    f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');
    let materials=0;f.s.materials=()=>{materials++;return [{id:'attachment-private',title:'不得读取的附件'}];};f.source.materials=async()=>{materials++;return [];};
    const exec={agent:{session:{id:'qx-content-watch'}}};
    for(const name of ['knowledge_start','knowledge_recall']){const result=await f.tools.get(name).execute({query:'偏好'},exec);assert.ok(!result.includes('不得读取'));assert.ok(!JSON.parse(result).error);}
    for(const entryId of ['attachment-private','memory-private'])assert.match(await f.tools.get('knowledge_read').execute({entryId},exec),/先检索|仅可读取/);
    assert.equal(caseReads,0);assert.equal(materials,0);
    const post=f.hooks.get('tools/post-execute');
    for(const name of ['mcp__qx_knowledge__list_knowledge','mcp__qx_knowledge__search_knowledge','mcp__qx_knowledge__read_knowledge','mcp__qx_knowledge__read_knowledge_citation','mcp__qx_case_memory__list_case_memories','mcp__qx_case_memory__recall_case_memory','mcp__qx_case_memory__read_case_memory']){
      const result=await post({...exec,name},{content:[{type:'text',text:'不可泄露私有正文'}]},async()=>({kind:'accept'}));
      assert.equal(result.kind,'block');assert.ok(!JSON.stringify(result).includes('不可泄露私有正文'));
    }
  }finally{f.close();}
});

test('内容会话不自动关联新建案件，也不继承父会话案件',async()=>{
  let managed=0;const f=fixture({inheritFrom:()=> 'parent',caseMemoryManage:async()=>{managed++;return {};}});try{
    f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');
    const parent=f.s.project({title:'父会话客户项目'});f.s.bind('parent',parent.id);f.source.list=async()=>[{id:'qx-content-watch'},{id:'parent'}];
    // Restore/legacy metadata must not turn a content session into automatic case scope.
    f.s.setting('automatic-scope:qx-content-watch','lawyer-content');
    const exec={agent:{session:{id:'qx-content-watch'}}};
    const resolved=await f.hooks.get('qx/knowledge/resolve-session')('qx-content-watch');assert.equal(resolved.project,'lawyer-content');assert.equal(await f.runner.ensureScope('qx-content-watch'),'lawyer-content');
    const created={id:'12345678-1234-1234-1234-123456789012',title:'新建客户案件'};
    const decision=await f.hooks.get('tools/post-execute')({...exec,name:'mcp__qx_legal__create_case'},{value:created,content:[]},async()=>({kind:'accept'}));
    assert.equal(decision.kind,'accept');assert.equal(f.s.binding('qx-content-watch'),'lawyer-content');assert.equal(managed,0);
  }finally{f.close();}
});

test('内容规则被撤回或读取期间归属变化时丢弃结果',async()=>{
  const f=fixture();try{
    f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');f.s.source('qx-content-watch','v1');
    f.s.upsertBatch('qx-content-watch','v1','own',[{kind:'preference',title:'表达偏好',content:'内容必须守住范围',sources:[{seq:1,quote:'偏好'}]}]);
    let own=f.s.list('lawyer-content')[0];own=f.s.review(own.id,{action:'confirm',revision:own.revision});
    const exec={agent:{session:{id:'qx-content-watch'}}};await f.tools.get('knowledge_recall').execute({query:'表达'},exec);
    f.s.review(own.id,{action:'reject',revision:own.revision});assert.match(await f.tools.get('knowledge_read').execute({entryId:own.id},exec),/仅可读取|不在可读取范围/);
    own=f.s.entry(own.id,'lawyer-content');own=f.s.review(own.id,{action:'confirm',revision:own.revision});
    const p=f.s.project({title:'另一项目'});f.source.current=async()=>{f.s.bind('qx-content-watch',p.id);return 'v1';};
    const result=await f.tools.get('knowledge_read').execute({entryId:own.id},exec);assert.ok(JSON.parse(result).error);assert.ok(!result.includes('内容必须守住范围'));
  }finally{f.close();}
});

test('内容分层读取按UTF-8共享16 KiB预算，自动消息不重置额度',async()=>{
  const f=fixture();try{
    f.services.get('qxKnowledge').ensureContentProject('qx-content-watch');f.s.source('qx-content-watch','v1');
    f.s.upsertBatch('qx-content-watch','v1','rules',Array.from({length:8},(_,index)=>({kind:'preference',title:'表达偏好'+index,content:('汉字内容'+index).repeat(500),sources:[{seq:1,quote:'偏好'}]})));
    const rows=f.s.list('lawyer-content');for(const row of rows)f.s.review(row.id,{action:'confirm',revision:row.revision});
    let turn=1;f.source.userTurn=async()=>turn;const exec={agent:{session:{id:'qx-content-watch'}}};let bytes=0;
    for(const [name,limit] of [['knowledge_start',4096],['knowledge_recall',6144]]){const output=await f.tools.get(name).execute({query:'表达'},exec);assert.ok(!JSON.parse(output).error);const size=Buffer.byteLength(output);assert.ok(size<=limit);bytes+=size;}
    let denied;
    for(const row of rows){const output=await f.tools.get('knowledge_read').execute({entryId:row.id},exec);if(JSON.parse(output).error){denied=row;assert.match(output,/16 KiB/);break;}assert.ok(Buffer.byteLength(output)<=4096);bytes+=Buffer.byteLength(output);}
    assert.ok(denied);assert.ok(bytes<=16384);turn=null;
    assert.match(await f.tools.get('knowledge_read').execute({entryId:denied.id},exec),/16 KiB/);
    turn=2;await f.tools.get('knowledge_recall').execute({query:'表达'},exec);assert.ok(!JSON.parse(await f.tools.get('knowledge_read').execute({entryId:denied.id},exec)).error);
  }finally{f.close();}
});
