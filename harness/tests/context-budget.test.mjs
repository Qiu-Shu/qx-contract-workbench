import test from 'node:test';import assert from 'node:assert/strict';
import {fixture} from './helpers.mjs';import {takeKnowledge,clipUtf8,jsonBytes,knowledgeLimits} from '../desktop/integration/knowledge-budget.mjs';
import {createSessionSource,digest} from '../desktop/integration/knowledge-runtime.mjs';
test('serialized UTF-8 budgets count Chinese, emoji, escapes and duplicates',()=>{
  assert.equal(clipUtf8('甲😀乙',6),'甲');assert.equal(clipUtf8('甲😀乙',7),'甲😀');const b={used:0};
  const item={text:'甲😀\n"'.repeat(200)};const output=takeKnowledge(b,item);assert.equal(b.used,Buffer.byteLength(output));
  assert.equal(JSON.parse(takeKnowledge(b,item)).alreadyReturned,true);assert.equal(b.used,Buffer.byteLength(output));
  assert.throws(()=>takeKnowledge(b,{text:'汉'.repeat(2000)}),/分层读取上限/);
  while(b.used+jsonBytes({text:'汉'.repeat(900),id:b.used})<=knowledgeLimits.turn)takeKnowledge(b,{text:'汉'.repeat(900),id:b.used});
  assert.throws(()=>takeKnowledge(b,{text:'汉'.repeat(900),id:b.used}),/16 KiB/);
});
test('native compaction preserves confirmations, attachment indexes and the actual user turn budget',async()=>{
  let compact=false;const ref={attachmentId:'sha256:'+'e'.repeat(64),name:'虚构合同.pdf',bytes:20};
  const source=createSessionSource({sessionQuery:{listSessions:async()=>[{header:{id:'a'}}],listEvents:async()=>[{seq:1,type:'user/message',surface:compact?'shadowed':'current'},...(compact?[{seq:2,type:'user/message',surface:'current'}]:[])],traceEvent:async()=>({replacementChain:[2]}),readEvent:async({seq})=>({target:{seq,type:'user/message',data:{source:{kind:seq===1?'user':'compact-checkpoint'},content:[{type:'text',text:seq===1?'虚构合同验收资料':'自动压缩'},{type:'file',attachment:ref}]}}})}});
  const f=fixture({source});try{await f.call('knowledge_start',{query:'合同'},'a');const project=f.store.binding('a'),entry=f.store.list(project)[0];f.store.review(entry.id,{project,revision:entry.revision,action:'confirm'});
    // Simulate the previous release's filtered-origin fingerprint without new raw metadata.
    f.store.setting('source-raw:a',null);f.store.db.prepare('UPDATE origins SET version=? WHERE session=?').run(digest(f.store.setting('source-meta:a')),'a');
    const post=f.listeners.get('tools/post-execute'),exec={name:'mcp__qx_knowledge__read_knowledge',agent:{session:{id:'a'}}},payload=n=>({content:[{type:'text',text:'A'.repeat(n)}],value:{content:[{type:'text',text:'A'.repeat(n)}]}});
    assert.equal((await post(exec,payload(9000),async()=>({kind:'accept'}))).kind,'accept');
    compact=true;assert.equal(await f.service.runner.fresh('a'),true);assert.equal(f.store.entry(entry.id,project).state,'confirmed');assert.equal(f.store.materials(project).length,1);
    assert.equal((await post(exec,payload(9001),async()=>({kind:'accept'}))).kind,'block');assert.equal(await source.userTurn('a'),1);
  }finally{f.service.dispose();}
});
test('old library tool outputs share the turn ceiling and preserve downstream blocks',async()=>{
  const f=fixture();try{f.add('a');const post=f.listeners.get('tools/post-execute'),exec={name:'mcp__qx_knowledge__read_knowledge_citation',agent:{session:{id:'a'}}};
    const decision=await post(exec,{content:[{type:'text',text:'原文'}],value:{structuredContent:{text:'中'.repeat(20000)}}},async()=>({kind:'accept'}));assert.equal(decision.kind,'block');assert.ok(jsonBytes(decision)<1000);assert.equal(decision.value,undefined);
    const denied={kind:'block',feedback:[{type:'text',text:'下游明确拒绝'}]};assert.equal(await post(exec,{},async()=>denied),denied);
  }finally{f.service.dispose();}
});

test('synthetic user messages cannot reset the last known real user turn budget',async()=>{
  let count=1;const source=createSessionSource({sessionQuery:{listSessions:async()=>[{header:{id:'a'}}],listEvents:async()=>Array.from({length:count},(_,i)=>({seq:i+1,type:'user/message',surface:'current'})),readEvent:async({seq})=>({target:{seq,type:'user/message',data:{source:{kind:seq===1?'user':'ptc-mode'},content:[]}}})}});
  const f=fixture({source});try{const post=f.listeners.get('tools/post-execute'),exec={name:'mcp__qx_knowledge__read_knowledge',agent:{session:{id:'a'}}},payload={content:[{type:'text',text:'A'.repeat(9000)}]};
    assert.equal((await post(exec,payload,async()=>({kind:'accept'}))).kind,'accept');count=65;
    assert.equal((await post(exec,payload,async()=>({kind:'accept'}))).kind,'block');
  }finally{f.service.dispose();}
});
test('three layers return small indexes, then matches, then one bounded source segment',async()=>{
  const f=fixture();try{f.add('a','虚构历史',Array.from({length:15},(_,i)=>({seq:i+1,role:'user',text:'合同验收😀\n'.repeat(300)})));
    const started=await f.call('knowledge_start',{query:'合同'},'a');assert.equal(started.error,undefined);assert.ok(jsonBytes(started)<=knowledgeLimits.start);
    const matched=await f.call('knowledge_recall',{query:'合同'},'a');assert.ok(Array.isArray(matched));assert.ok(jsonBytes(matched)<=knowledgeLimits.recall);
    const part=await f.call('knowledge_read',{entryId:matched[0].id,source:true},'a');assert.equal(part.error,undefined);assert.ok(jsonBytes(part)<=knowledgeLimits.read);assert.equal(part.snippets.length,1);assert.ok(part.snippets[0].next>0);
    const again=await f.call('knowledge_read',{entryId:matched[0].id,source:true},'a');assert.equal(again.alreadyReturned,true);
  }finally{f.service.dispose();}
});

test('confirmed first-layer rules survive crowded task indexes without including their bodies',async()=>{
  const f=fixture();try{f.add('a');await f.service.runner.run({incremental:true});const project=f.store.binding('a'),version=await f.source.current('a');
    const ids=f.store.upsertBatch('a',version,'fixture-rules',Array.from({length:6},(_,i)=>({kind:'rule',title:`虚构规则${i}`,content:'完整规则正文不应自动加载'.repeat(100),sources:[{seq:1,quote:'合同'}]})));
    for(const id of ids)f.store.review(id,{project,revision:1,action:'confirm'});
    for(let i=0;i<8;i++)f.store.resource(project,{document:`doc-${i}`,title:'虚构合同资料'.repeat(15)});
    const start=await f.call('knowledge_start',{query:'合同'},'a'),context=JSON.parse(start.memory);
    assert.equal(start.error,undefined);assert.ok(jsonBytes(start)<=4096);assert.equal(context.layer1.length,4);assert.equal(start.morePrinciples,true);
    assert.ok(context.layer1.every(e=>e.state==='confirmed'&&!Object.hasOwn(e,'content')));assert.ok(!JSON.stringify(start).includes('完整规则正文'));
    const rule=await f.call('knowledge_read',{entryId:context.layer1[0].id},'a');assert.match(rule.content,/完整规则正文/);assert.ok(jsonBytes(rule)<=4096);
  }finally{f.service.dispose();}
});

test('appending beyond the foreground threshold keeps existing attachments visible before background rescan',async()=>{
  let count=1;const ref={attachmentId:'sha256:'+'d'.repeat(64),name:'虚构合同.pdf',bytes:20};
  const source=createSessionSource({sessionQuery:{listSessions:async()=>[{header:{id:'a'}}],listEvents:async()=>Array.from({length:count},(_,i)=>({seq:i+1,type:'user/message',surface:'current'})),readEvent:async({seq})=>({target:{seq,type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:'虚构合同'},...(seq===1?[{type:'file',attachment:ref}]:[])]}}})}});
  const f=fixture({source});try{await f.service.runner.run({incremental:true});const project=f.store.binding('a');assert.equal(f.store.materials(project).length,1);
    count=61;await f.service.runner.syncProjectMaterials(project,{foreground:true});assert.equal(f.store.materials(project).length,1);
    const state=await(await f.request('list?project='+project)).json();assert.equal(state.materials.length,1);
  }finally{f.service.dispose();}
});
