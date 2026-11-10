import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './helpers.mjs';
test('new work can recall its own source-backed records without manually creating or binding a project',async()=>{
  const f=fixture();try{
    f.add('session-a');
    const result=await f.call('knowledge_start',{query:'验收期限'},'session-a');
    assert.equal(result.error,undefined);
    assert.notEqual(f.store.binding('session-a'),'inbox');
    const matches=await f.call('knowledge_recall',{query:'验收期限'},'session-a');
    assert.ok(matches.some(m=>m.content.includes('验收期限')));
    assert.equal(f.modelCalls,0);
  }finally{f.service.dispose();}
});
test('scope correction has stale-write protection and can be undone without approving old facts',async()=>{
  const f=fixture();try{
    f.add('a');await f.call('knowledge_start',{query:'合同'},'a');const before=await (await f.request('state?sessionId=a')).json();
    f.store.project({id:'case-2',title:'另一个明确案件'});
    const moved=await f.request('bind',{session:'a',project:'case-2',expectedProject:before.project,revision:before.binding?.revision});assert.equal(moved.status,200);
    const stale=await f.request('bind',{session:'a',project:before.project,expectedProject:before.project,revision:before.binding?.revision});assert.equal(stale.status,409);
    const after=await(await f.request('state?sessionId=a')).json();
    assert.equal((await f.request('undo-bind',{session:'a',revision:after.binding.revision})).status,200);assert.equal(f.store.binding('a'),before.project);
    assert.ok(f.store.list(before.project).every(e=>e.state!=='confirmed'));
  }finally{f.service.dispose();}
});
test('correcting an automatic excerpt does not silently mark it as a confirmed fact',async()=>{
  const f=fixture();try{
    f.add('a');await f.call('knowledge_start',{query:'合同'},'a');const entry=f.store.list(f.store.binding('a'))[0];
    const response=await f.request('review',{entryId:entry.id,project:entry.project,revision:entry.revision,action:'edit',content:'客户补充：尚未签约。'});
    const edited=await response.json();assert.equal(edited.state,'active');assert.equal(f.store.history(entry.id,entry.project).length,1);
  }finally{f.service.dispose();}
});
test('same titles stay private, existing case binding wins, repeated recall does not duplicate records',async()=>{
  const f=fixture();try{
    f.add('a','同名客户',[{seq:1,role:'user',text:'苹果项目交付期限三天。'}]);f.add('b','同名客户',[{seq:1,role:'user',text:'香蕉项目交付期限十天。'}]);
    await Promise.all([f.call('knowledge_start',{query:'交付期限'},'a'),f.call('knowledge_start',{query:'交付期限'},'b')]);
    assert.equal(f.store.list(f.store.binding('b')).length,1,'simultaneous work must both finish initial capture');
    assert.notEqual(f.store.binding('a'),f.store.binding('b'));
    const list=await f.call('knowledge_recall',{query:'苹果 香蕉'},'b');assert.ok(list.every(e=>!e.content.includes('苹果')));
    const before=f.store.list(f.store.binding('a')).length;await f.call('knowledge_start',{query:'交付期限'},'a');assert.equal(f.store.list(f.store.binding('a')).length,before);
    f.store.project({id:'verified-case',title:'律师明确选择的案件'});f.store.bind('a','verified-case');
    await f.service.runner.ensureScope('a');assert.equal(f.store.binding('a'),'verified-case');
  }finally{f.service.dispose();}
});
test('automatic work titles improve when metadata arrives without overwriting a manually renamed work',async()=>{
  const f=fixture();try{f.add('a','');const project=await f.service.runner.ensureScope('a');
    f.sessions.get('a').title='设备采购验收审查';await f.service.runner.ensureScope('a');assert.equal(f.store.getProject(project).title,'设备采购验收审查');
    f.store.project({...f.store.getProject(project),title:'律师手工命名'});f.sessions.get('a').title='新的对话标题';await f.service.runner.ensureScope('a');assert.equal(f.store.getProject(project).title,'律师手工命名');
  }finally{f.service.dispose();}
});
test('confirmed handoff inherits scope even when first opening already created a task scope',async()=>{
  let parent;const f=fixture({inheritFrom:()=>parent});try{
    f.add('intake');f.add('case');await f.service.runner.ensureScope('case');parent='intake';
    await f.service.runner.ensureScope('case');assert.equal(f.store.binding('case'),f.store.binding('intake'));
  }finally{f.service.dispose();}
});
test('local incremental capture preserves every short message in a long batch and does not call a model',async()=>{
  const f=fixture();try{
    f.add('long','长记录',Array.from({length:25},(_,i)=>({seq:i+1,role:'user',text:`第${i+1}份虚构证据需核实。`})));
    await f.service.runner.run({incremental:true});
    const rows=f.store.list(f.store.binding('long'));assert.equal(rows.length,25);assert.ok(rows.some(r=>r.content.includes('第13份')));assert.equal(f.modelCalls,0);
  }finally{f.service.dispose();}
});
test('disabled automation stays disabled and rejects unknown summary modes',async()=>{
  const f=fixture();try{
    f.add('off');await f.request('settings',{enabled:false});await f.call('knowledge_start',{query:'合同'},'off');
    assert.equal(f.store.list(f.store.binding('off')).length,0);
    assert.equal((await f.request('settings',{summaryMode:'unknown'})).status,400);
  }finally{f.service.dispose();}
});
test('editing or deleting source revokes old excerpts and cannot turn assistant analysis into confirmed facts',async()=>{
  const f=fixture();try{
    f.add('edit','核对',[{seq:1,role:'assistant',text:'可能存在违约，尚待核实。'}]);await f.call('knowledge_start',{query:'违约'},'edit');
    const old=f.store.list(f.store.binding('edit'))[0];assert.equal(old.state,'active');assert.match(old.content,/助手分析（待核对）/);
    f.sessions.get('edit').messages[0].text='已修改为：材料不足。';
    const matches=await f.call('knowledge_recall',{query:'违约'},'edit');assert.equal(matches.length,0);assert.equal(f.store.entry(old.id,old.project).state,'invalid');
    f.sessions.delete('edit');await f.service.runner.reconcile();assert.equal(f.store.entry(old.id,old.project).content,'');
  }finally{f.service.dispose();}
});
