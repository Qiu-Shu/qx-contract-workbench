import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {apply} from './index.mjs';

test('real parser and official title stream persist the attachment topic without reading later input',async()=>{
  const workspace=await mkdtemp(join(tmpdir(),'qx-title-'));
  const source=join(workspace,'材料.txt');await writeFile(source,'虚构星河公司设备采购合同，约定验收后支付货款。');
  const handlers=new Map(),cleanups=[],events=[],warnings=[];let requests=0,resolveDone;
  const done=new Promise(resolve=>resolveDone=resolve);
  const session={id:'synthetic-title',header:{},snapshotEvents:()=>[...events],
    requestHeader:()=>({config:{provider:'offline-test',model:'deterministic'}}),
    append(type,data){const event={seq:events.length,type,data};events.push(event);handlers.get('session/event')?.(session,event);if(type==='session/title')resolveDone(data)}};
  const ctx={on:(name,fn)=>handlers.set(name,fn),effect:fn=>cleanups.push(fn()),
    logger:{warn:message=>{warnings.push(message);resolveDone(null)}},sessions:{get:()=>session},
    sessionTitle:{get:()=>events.findLast(e=>e.type==='session/title')?.data},
    attachments:{fileHostPath:()=>source},
    llm:{async prepareCall(config){return {config,async *stream(options){
      requests++;assert.match(options.messages[0].content[0].text,/设备采购合同/);
      assert.doesNotMatch(options.messages[0].content[0].text,/第二份/);
      yield {type:'text-delta',index:0,text:'**星河设备采购合同审查**\n其他说明'};
      yield {type:'finish',reason:{kind:'stop'}};
    }}}}};
  try{
    apply(ctx,{workspace,python:'D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe'});
    session.append('user/message',{source:{kind:'user'},content:[{type:'file',attachment:{name:'材料.txt'}}]});
    session.append('user/message',{source:{kind:'user'},content:[{type:'text',text:'第二份不同材料'}]});
    const result=await Promise.race([done,new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('title timeout')),10000);timer.unref()})]);
    assert.deepEqual(warnings,[]);assert.equal(result.title,'星河设备采购合同审查');
    assert.deepEqual(result.messageSeqs,[0]);assert.equal(requests,1);
    assert.equal(events.filter(e=>e.type==='session/title-llm-request').length,1);
  }finally{for(const cleanup of cleanups)await cleanup?.();assert.ok(workspace.startsWith(join(tmpdir(),'qx-title-')));await rm(workspace,{recursive:true,force:true})}
});
