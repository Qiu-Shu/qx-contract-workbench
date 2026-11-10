import test from 'node:test';import assert from 'node:assert/strict';
import {fixture} from './helpers.mjs';import {createSessionSource} from '../desktop/integration/knowledge-runtime.mjs';
test('switching model mode to local aborts queued paid work',async()=>{
  let release,started,calls=0;const gate=new Promise(r=>release=r),ready=new Promise(r=>started=r);
  const f=fixture({model:async({batch})=>{calls++;started();await gate;return {items:[{kind:'summary',title:'虚构摘要',content:'待核对',sources:[{seq:batch[0].seq,quote:batch[0].text.slice(0,20)}]}]};}});
  try{f.add('a','长记录',Array.from({length:30},(_,i)=>({seq:i+1,role:'user',text:'虚构材料'.repeat(400)})));await f.request('settings',{summaryMode:'model'});const running=f.service.runner.run();await ready;await f.request('settings',{summaryMode:'local'});release();await running;assert.equal(calls,1);}finally{release?.();f.service.dispose();}
});
test('confirmed handoff can be captured in its first background pass',async()=>{
  const f=fixture({inheritFrom:s=>s==='child'?'intake':null});try{f.add('intake');f.add('child');const r=await f.service.runner.run({incremental:true});assert.equal(r.failed,0);assert.ok(f.store.list(f.store.binding('child')).some(e=>e.session==='child'));}finally{f.service.dispose();}
});
test('long work with many attachments returns bounded useful context and retrieves attachments beyond page one',async()=>{
  const f=fixture();try{f.add('a','历史',Array.from({length:8},(_,i)=>({seq:i+1,role:'user',text:'虚构验收材料'.repeat(450)})));
    f.sessions.get('a').materials=Array.from({length:51},(_,i)=>({seq:i===50?1:8,attachment:{attachmentId:'sha256:'+i.toString(16).padStart(64,'0'),name:i===50?'目标证据.pdf':`虚构合同${i}.pdf`,bytes:10}}));
    const start=await f.call('knowledge_start',{query:'验收'},'a');assert.equal(start.error,undefined);assert.ok(JSON.stringify(start).length<15000);
    const recalled=await f.call('knowledge_recall',{query:'目标证据'},'a');const found=recalled.find(m=>m.title==='目标证据.pdf');assert.ok(found);
    const read=await f.call('knowledge_read',{entryId:found.id},'a');assert.equal(read.error,undefined);assert.equal(read.title,'目标证据.pdf');
  }finally{f.service.dispose();}
});
test('opening a long-history list does not scan message bodies in the foreground',async()=>{
  let reads=0;const events=Array.from({length:1000},(_,i)=>({seq:i+1,type:'user/message',surface:'current'}));
  const source=createSessionSource({sessionQuery:{listSessions:async()=>[{header:{id:'large'}}],listEvents:async()=>events,readEvent:async({seq})=>{reads++;return {target:{seq,type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:'独立虚构测试'}]}}};}}});
  const f=fixture({source});try{await f.service.runner.ensureScope('large');const response=await f.request('list?project='+f.store.binding('large'));assert.equal(response.status,200);assert.equal(reads,0);}finally{f.service.dispose();}
});
test('sent images have private source-backed indexes and use native image paths',async()=>{
  const ref={attachmentId:'sha256:'+'f'.repeat(64),mediaType:'image/png',width:100,height:80,bytes:800};let deleted=false;
  const source=createSessionSource({sessionQuery:{listSessions:async()=>[{header:{id:'picture'}}],listEvents:async()=>deleted?[]:[{seq:1,type:'user/message',surface:'current'}],readEvent:async()=>({target:{seq:1,type:'user/message',data:{source:{kind:'user'},content:[{type:'image',attachment:ref}]}}})},attachments:{imageHostPath:()=>'/fixture/image-object',fileHostPath:()=>{throw Error('wrong attachment method');}}});
  const f=fixture({source});try{const result=await f.call('knowledge_start',{query:'图片'},'picture');assert.equal(result.materials.length,1);const read=await f.call('knowledge_read',{entryId:result.materials[0].id},'picture');assert.equal(read.path,'/fixture/image-object');deleted=true;assert.equal((await f.call('knowledge_start',{query:'图片'},'picture')).materials.length,0);}finally{f.service.dispose();}
});
