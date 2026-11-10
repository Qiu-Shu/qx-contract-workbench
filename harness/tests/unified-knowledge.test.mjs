import test from 'node:test';import assert from 'node:assert/strict';import {fixture} from './helpers.mjs';
const caseId='11111111-1111-4111-8111-111111111111',memoryId='22222222-2222-4222-8222-222222222222';
function provider(){let revision=1,content='虚构验收：五月十日交付',stale=false;const calls=[];
  const row=()=>({id:memoryId,case_id:caseId,kind:'selected_note',revision,content,source_note_id:'note-fixture',source_stale:stale,source:{label:'虚构客户记录',snapshot:'原话：五月十日交付',note_id:'note-fixture'},updated_at:'2026-11-10T00:00:00Z'});
  return {calls,row,setStale:()=>stale=true,read:async(action,args)=>{calls.push({action,args});assert.equal(args.case_id,caseId);return action==='read'?row():{memories:[row(),{...row(),id:'33333333-3333-4333-8333-333333333333'}],matches:[row()],next_offset:null};},manage:async(action,args)=>{calls.push({action,args});if(action==='list_cases')return {cases:[{id:caseId,title:'虚构案件'}],next_offset:null};if(action==='status')return {case_id:args.case_id,enabled:true};assert.equal(args.case_id,caseId);if(action==='update'){assert.equal(args.revision,revision);content=args.content;revision++;return {memory:row()};}throw Error('unexpected action');}};
}
test('one work feed includes selected case memories, deduplicates same sources and preserves source/state',async()=>{
  const p=provider(),f=fixture({caseMemory:p.read,caseMemoryManage:p.manage});try{f.add('a');f.store.project({id:caseId,title:'虚构案件'});f.store.bind('a',caseId);
    const page=await(await f.request('list?project='+caseId+'&query=验收')).json();assert.equal(page.memories.items.length,1);assert.equal(page.memories.items[0].state,'saved');
    const detail=await(await f.request('memory?project='+caseId+'&memoryId='+memoryId)).json();assert.equal(detail.sourceLabel,'虚构客户记录');
    const changed=await f.request('memory-review',{project:caseId,memoryId,revision:1,content:'纠正：六月十日交付'});assert.equal(changed.status,200);assert.equal(p.row().revision,2);assert.equal(p.row().source.snapshot,'原话：五月十日交付');
    const trace=await(await f.request('memory?project='+caseId+'&memoryId='+memoryId+'&source=true')).json();assert.equal(trace.content,'原话：五月十日交付');
    p.setStale();assert.equal((await f.request('memory?project='+caseId+'&memoryId='+memoryId)).status,409);
  }finally{f.service.dispose();}
});
test('existing cases appear without creating copies and viewing one does not rebind the active work',async()=>{
  const p=provider(),f=fixture({caseMemory:p.read,caseMemoryManage:p.manage});try{f.add('a');const initial=await(await f.request('state?sessionId=a')).json();assert.equal(initial.cases[0].id,caseId);
    const response=await f.request('case-scope',{caseId,title:'虚构案件'});assert.equal(response.status,200);assert.equal(f.store.binding('a'),initial.project);assert.equal(f.store.list(caseId).length,0);
  }finally{f.service.dispose();}
});
test('case creation waits for association before returning and preserves manually selected work',async()=>{
  const p=provider();let release,entered=false;const gate=new Promise(r=>release=r);
  const f=fixture({caseMemory:p.read,caseMemoryManage:async(action,args)=>{if(action==='status'){entered=true;await gate;}return p.manage(action,args);}});try{f.add('a');await f.service.runner.ensureScope('a');const handler=f.listeners.get('tools/post-execute'),exec={name:'mcp__qx_legal__create_case',agent:{session:{id:'a'}}},result={value:{structuredContent:{id:caseId,title:'虚构案件'}}};
    let finished=false;const pending=handler(exec,result,async()=>({kind:'accept'})).then(r=>{finished=true;return r;});
    await new Promise(r=>setImmediate(r));assert.equal(entered,true);assert.equal(finished,false);release();assert.equal((await pending).kind,'accept');assert.equal(f.store.binding('a'),caseId);
    assert.equal((await handler({...exec,name:'mcp__qx_case_memory__read_case_memory'},{value:{case_id:caseId,content:'本案记忆'},content:[]},async()=>({kind:'accept'}))).kind,'accept');
    f.store.project({id:'manual-work',title:'人工指定工作'});f.store.bind('a','manual-work');await handler(exec,result,async()=>({kind:'accept'}));assert.equal(f.store.binding('a'),'manual-work');
  }finally{f.service.dispose();}
});
test('deduplication keeps separate revisions and source fingerprints',async()=>{
  const p=provider(),row=p.row(),f=fixture({caseMemory:async()=>({memories:[row,{...row,id:'duplicate'}, {...row,id:'revision',revision:2},{...row,id:'source-change',source:{...row.source,sha256:'different'}}]})});
  try{f.store.project({id:caseId,title:'虚构案件'});const page=await(await f.request('list?project='+caseId)).json();assert.equal(page.memories.items.length,3);assert.deepEqual(page.memories.items.map(m=>m.revision),[1,2,1]);}finally{f.service.dispose();}
});
test('legacy case memory rejects stale sources in rendered and canonical payloads',async()=>{
  const f=fixture();try{f.add('a');f.store.project({id:caseId,title:'虚构案件'});f.store.bind('a',caseId);const handler=f.listeners.get('tools/post-execute');
    for(const name of ['read_case_memory','list_case_memories'])for(const format of ['value','content']){
      const row={case_id:caseId,source_stale:true,content:'撤销的旧正文'},data=name==='list_case_memories'?{case_id:caseId,memories:[row]}:row;
      const result=format==='value'?{value:{structuredContent:data},content:[{type:'text',text:'显示摘要'}]}:{content:[{type:'text',text:JSON.stringify(data)}]};
      const r=await handler({name:'mcp__qx_case_memory__'+name,agent:{session:{id:'a'}}},result,async()=>({kind:'accept'}));assert.equal(r.kind,'block');assert.match(r.feedback[0].text,/来源/);assert.equal(r.value,undefined);
    }
  }finally{f.service.dispose();}
});
test('legacy case-memory payloads share native knowledge budget and cannot return oversize canonical values',async()=>{
  const f=fixture();try{f.add('a');f.store.project({id:caseId,title:'虚构案件'});f.store.bind('a',caseId);const post=f.listeners.get('tools/post-execute'),exec={name:'mcp__qx_case_memory__read_case_memory',agent:{session:{id:'a'}}};
    const result=await post(exec,{content:[{type:'text',text:'短显示'}],value:{structuredContent:{case_id:caseId,content:'原文'.repeat(5000)}}},async()=>({kind:'accept'}));assert.equal(result.kind,'block');assert.match(result.feedback[0].text,/预算/);assert.equal(result.value,undefined);
    const small={content:[{type:'text',text:'短显示'}],value:{structuredContent:{case_id:caseId,content:'a'.repeat(9000)}}};assert.equal((await post(exec,small,async()=>({kind:'accept'}))).kind,'accept');
    assert.equal((await post({...exec,name:'mcp__qx_knowledge__read_knowledge'},{content:[{type:'text',text:'b'.repeat(9000)}]},async()=>({kind:'accept'}))).kind,'block');
    assert.equal((await post(exec,{content:[],value:{case_id:'other-case',content:'跨案'}},async()=>({kind:'accept'}))).kind,'block');
  }finally{f.service.dispose();}
});
