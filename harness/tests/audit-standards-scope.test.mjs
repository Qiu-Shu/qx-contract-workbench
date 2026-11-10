import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './helpers.mjs';

for(const returnToOriginal of [false,true])test(returnToOriginal?'an A-to-B-to-A scope change cannot revive the original in-flight read':'an in-flight case-memory read cannot adopt a later calls mutable scope',async()=>{
  const caseA='11111111-1111-4111-8111-111111111111',caseB='22222222-2222-4222-8222-222222222222',memoryId='33333333-3333-4333-8333-333333333333';
  let release,entered,hold=false;
  const gate=new Promise(resolve=>release=resolve),ready=new Promise(resolve=>entered=resolve);
  const row={id:memoryId,case_id:caseA,content:'合成案件A专属正文',revision:1,kind:'manual',source:{snapshot:'合成来源'}};
  const f=fixture({caseMemory:async(action,args)=>{
    if(args.case_id!==caseA)return {memories:[],matches:[]};
    if(action==='read'){if(hold){entered();await gate;}return row;}
    return {memories:[row],matches:[row]};
  }});
  try{
    f.add('session');f.store.project({id:caseA,title:'合成A'});f.store.project({id:caseB,title:'合成B'});f.store.bind('session',caseA);
    await f.call('knowledge_recall',{query:'专属'},'session');hold=true;
    const pending=f.call('knowledge_read',{entryId:'memory-'+memoryId},'session');await ready;
    f.store.bind('session',caseB);await f.call('knowledge_start',{query:'合成B'},'session');
    if(returnToOriginal){f.store.bind('session',caseA);await f.call('knowledge_start',{query:'合成A'},'session');}
    release();
    const result=await pending;assert.ok(result.error,'scope change must reject the earlier A result');
    assert.equal(result.content,undefined);
  }finally{release?.();f.service.dispose();}
});

test('scope changes keep the shared turn byte budget and a genuine user turn renews it',async()=>{
  const f=fixture();
  try{
    f.add('session');f.store.project({id:'case-a',title:'合成A'});f.store.project({id:'case-b',title:'合成B'});f.store.bind('session','case-a');
    const handler=f.listeners.get('tools/post-execute'),exec={name:'mcp__qx_knowledge__read_knowledge',agent:{session:{id:'session'}}};
    const read=async n=>handler(exec,{content:[{type:'text',text:'a'.repeat(n)}]},async()=>({kind:'accept'}));
    assert.equal((await read(9000)).kind,'accept');
    f.store.bind('session','case-b');assert.equal((await read(5000)).kind,'accept');
    f.store.bind('session','case-a');assert.equal((await read(4000)).kind,'block','returning to A must retain the 14000-byte usage');
    f.sessions.get('session').messages.push({seq:2,role:'user',text:'新的合成用户任务'});
    assert.equal((await read(9000)).kind,'accept','an actual new user turn should renew the allowance');
  }finally{f.service.dispose();}
});
