import test from 'node:test';
import assert from 'node:assert/strict';
import {MessageCoalescer, messageControl} from '../qx-coalescer.js';

function clock(){let now=0,id=0;const timers=new Map();return{now:()=>now,setTimer:(fn,ms)=>{timers.set(++id,{fn,at:now+ms});return id;},clearTimer:key=>timers.delete(key),async advance(ms){now+=ms;for(let n=0;n<30;n++){const due=[...timers].find(([,v])=>v.at<=now);if(!due)break;timers.delete(due[0]);await due[1].fn();await Promise.resolve();}}};}
const item=(id,text,media=false)=>({id,key:'owner/session',sessionId:'session',accountId:'owner',text,lines:[text],hasMedia:media});
async function setup(options={}){const time=clock(),calls=[],saved=[];const queue=new MessageCoalescer({process:async b=>{calls.push(b);},persist:async s=>saved.push(structuredClone(s)),...time,...options});await queue.recover();queue.resume();return{queue,time,calls,saved};}

test('quiet window merges ordered text and attachment, duplicate IDs never double process',async()=>{
 const {queue,time,calls}=await setup();await queue.add(item('1','审查合同'));await time.advance(2000);await queue.add(item('2','附件路径',true));assert.equal(await queue.add(item('2','重复')),false);
 await time.advance(11999);assert.equal(calls.length,0);await time.advance(1);assert.deepEqual(calls[0].items.map(x=>x.id),['1','2']);await queue.idle();assert.equal(queue.snapshot().active,false);
});
test('receiving remains free while model is busy; next burst is one sequential batch',async()=>{
 let finish;const calls=[];const {queue,time}=await setup({process:async b=>{calls.push(b);if(calls.length===1)await new Promise(r=>{finish=r;});}});
 await queue.add(item('1','第一件事'));await time.advance(8000);await queue.add(item('2','第二件事'));await queue.add(item('3','补充'));await time.advance(8000);assert.equal(calls.length,1);assert.equal(queue.snapshot().pendingMessages,2);finish();await queue.idle();await time.advance(0);await queue.idle();assert.equal(calls.length,2);assert.deepEqual(calls[1].items.map(x=>x.id),['2','3']);
});
test('explicit hold survives elapsed time and attachments; affirmative release flushes',async()=>{
 const {queue,time,calls}=await setup();await queue.add(item('1','还没发完，请稍等'));await queue.add(item('2','材料',true));await time.advance(600000);assert.equal(calls.length,0);assert.equal(queue.snapshot().held,true);await queue.add(item('3','如果发完了再开始'));await time.advance(30000);assert.equal(calls.length,0);await queue.add(item('4','发完了，请开始'));await time.advance(0);await queue.idle();assert.equal(calls.length,1);assert.equal(calls[0].items.length,4);
});
test('negation, questions and quoted contract text are not readiness release',()=>{
 for(const s of ['还没发完','不要开始','如果发完了再开始','现在可以开始吗？','合同原文：“请开始处理”'])assert.notEqual(messageControl(s),'release',s);
 assert.equal(messageControl('这些是附件。先别处理'),'hold');assert.equal(messageControl('已经发完了，请开始处理。'),'release');
});
test('pending recovers, dispatched failures remain inspectable and are never automatically replayed',async()=>{
 const state={version:1,pending:[{id:'p',key:'owner/session',items:[item('1','待处理')],firstAt:0,dueAt:8000,held:false}],active:{id:'a',items:[item('old','已发送')],sessionId:'session'},history:[],failed:[]};
 const {queue,time,calls,saved}=await setup({state});await time.advance(8000);await queue.idle();assert.equal(calls.length,1);assert.equal(calls[0].id,'p');assert.equal(saved.at(-1).failed[0].status,'interrupted');assert.equal(await queue.add(item('old','重复')),false);
});
test('processing failure is recorded once, later messages can proceed without replay',async()=>{
 const {queue,time,saved}=await setup({process:async()=>{throw Error('synthetic failure');}});await queue.add(item('1','失败'));await time.advance(8000);await queue.idle();assert.equal(queue.snapshot().failed,1);assert.equal(saved.at(-1).failed[0].error,'synthetic failure');assert.equal(await queue.add(item('1','重复')),false);
});
test('poll containing slow media does not split while ingestion is active; pause retains pending',async()=>{
 const {queue,time,calls}=await setup();queue.beginReceive();await queue.add(item('1','合同'));await time.advance(10000);assert.equal(calls.length,0);await queue.add(item('2','附件',true));queue.endReceive();queue.pause();await time.advance(12000);assert.equal(calls.length,0);queue.resume();await time.advance(0);await queue.idle();assert.equal(calls.length,1);
});


test('continuous input keeps resetting the quiet window beyond thirty seconds',async()=>{
 const {queue,time,calls}=await setup();for(let i=0;i<10;i++){await queue.add(item(String(i),'补充'));await time.advance(7000);}assert.equal(calls.length,0);await time.advance(1000);await queue.idle();assert.equal(calls.length,1);assert.equal(calls[0].items.length,10);
});
test('a failed durable accept can be retried without losing or duplicating the message',async()=>{
 let fail=true;const {queue,time,calls}=await setup({persist:async()=>{if(fail)throw Error('disk unavailable');}});
 await assert.rejects(queue.add(item('1','材料')),/disk/);assert.equal(queue.has('1'),false);fail=false;await queue.add(item('1','材料'));await time.advance(8000);await queue.idle();assert.equal(calls.length,1);
});
