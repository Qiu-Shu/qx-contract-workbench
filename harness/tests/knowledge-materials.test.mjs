import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './helpers.mjs';
import {createSessionSource} from '../desktop/integration/knowledge-runtime.mjs';
const material=(hash,name='合同.docx',seq=1)=>({seq,attachment:{attachmentId:'sha256:'+hash.repeat(64),name,bytes:42}});
test('native sources index only current sent attachment references, not text paths or compacted copies',async()=>{
  const ref=material('a').attachment;
  const events=[{seq:1,type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:'C:/private/secret.docx'},{type:'file',attachment:ref},{type:'file',attachment:{...ref,name:'../secret'}}]}},
    {seq:2,type:'user/message',data:{source:{kind:'compact-checkpoint'},content:[{type:'file',attachment:ref}]}},
    {seq:3,type:'assistant/message',data:{message:{content:[{type:'text',text:'这是助手推测。'}]}}}];
  const source=createSessionSource({sessionQuery:{listSessions:async()=>[{header:{id:'native'}}],readTitleSnapshot:async()=>({title:{title:'虚构案件审查'}}),listEvents:async()=>events.map(e=>({seq:e.seq,type:e.type,surface:'current'})),readEvent:async({seq})=>({target:events.find(e=>e.seq===seq)})},attachments:{fileHostPath:attachment=>'fixture/'+attachment.name}});
  const d=await source.describe('native');assert.deepEqual(d.records.map(r=>r.seq),[1,3]);assert.equal(await source.title('native'),'虚构案件审查');
  const materials=await source.materials('native',d);assert.equal(materials.length,1);assert.equal(source.materialPath(materials[0].attachment),'fixture/合同.docx');
  const messages=[];for await(const m of source.messages('native',d))messages.push(m);assert.deepEqual(messages.map(m=>m.role),['user','assistant']);
});
test('library linking uses captured work revision and refuses a move during upload',async()=>{
  const f=fixture();try{f.add('a');const scope=await f.listeners.get('qx/knowledge/resolve-session')('a');
    await f.listeners.get('qx/knowledge/document')({session:'a',scope,document:'doc-a',title:'虚构合同.docx'});assert.equal(f.store.resources(scope.project).length,1);
    f.store.project({id:'case-b',title:'另一案件'});f.store.bind('a','case-b');
    await assert.rejects(f.listeners.get('qx/knowledge/document')({session:'a',scope,document:'doc-b',title:'虚构合同.docx'}),/归属已变化/);assert.equal(f.store.resources('case-b').length,0);
  }finally{f.service.dispose();}
});
test('sent attachments are automatically indexed once by hash and same-name revisions remain visible',async()=>{
  const f=fixture();try{
    f.add('a');f.sessions.get('a').materials=[material('a'),material('a'),material('b')];
    const start=await f.call('knowledge_start',{query:'合同'},'a');
    assert.equal(start.materials?.length,2);assert.ok(start.materials.every(m=>m.versions===2));
    assert.equal(start.materials[0].category,'合同与协议');
    const again=await f.call('knowledge_start',{query:'合同'},'a');assert.equal(again.alreadyReturned,true);assert.equal(f.store.materials(f.store.binding('a')).length,2);
    f.add('b');const other=await f.call('knowledge_start',{query:'合同'},'b');assert.equal(other.materials.length,0);
  }finally{f.service.dispose();}
});
test('editing away an attachment removes it from recall without deleting its original',async()=>{
  const f=fixture();try{
    f.add('a');f.sessions.get('a').materials=[material('a')];await f.call('knowledge_start',{query:'合同'},'a');
    f.sessions.get('a').materials=[];f.sessions.get('a').messages[0].text='附件已经撤回。';
    const next=await f.call('knowledge_start',{query:'合同'},'a');assert.equal(next.materials.length,0);
  }finally{f.service.dispose();}
});
test('same-task source tracing needs no separate UI grant but cross-task source tracing stays denied',async()=>{
  const f=fixture();try{
    f.add('a');await f.call('knowledge_start',{query:'验收'},'a');const [entry]=await f.call('knowledge_recall',{query:'验收'},'a');
    const trace=await f.call('knowledge_read',{entryId:entry.id,source:true},'a');assert.equal(trace.error,undefined);assert.ok(trace.snippets[0].text.includes('验收'));
    f.add('b');const denied=await f.call('knowledge_read',{entryId:entry.id,source:true},'b');assert.ok(denied.error);
  }finally{f.service.dispose();}
});
