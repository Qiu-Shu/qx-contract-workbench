import test from 'node:test';
import assert from 'node:assert/strict';
import {installNaming, titleInput} from './naming.mjs';

function harness(generate) {
  const handlers = new Map(), live = new Map(), cleanups = [];
  const ctx = {on: (name, fn) => handlers.set(name, fn), effect: fn => cleanups.push(fn()),
    sessions: {get: id => live.get(id)}, logger: {warn(){}},
    sessionTitle: {get: session => session.events.findLast(e => e.type === 'session/title')?.data}};
  installNaming(ctx, generate);
  const emit = (session, type, data) => {
    const event = {seq: session.events.length, type, data}; session.events.push(event);
    handlers.get('session/event')?.(session, event); return event;
  };
  const session = id => {
    const value = {id, header: {}, events: [], snapshotEvents(){return [...this.events]},
      requestHeader(){return {config:{provider:'test',model:'test'}}},
      append(type,data){emit(this,type,data)}};
    live.set(id,value);return value;
  };
  const message = (s, content) => emit(s,'user/message',{source:{kind:'user'},content});
  return {session,message,emit,live,close:async()=>{for(const f of cleanups)await f?.()}};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const text = value => [{type:'text',text:value}];
const title = s => s.events.findLast(e=>e.type==='session/title')?.data.title;

test('three parallel conversations keep their first contents despite out-of-order completion',async()=>{
  const pending = new Map();
  const h=harness((s,first)=>new Promise(resolve=>pending.set(s.id,()=>resolve(first.data.content[0].text+'摘要'))));
  const sessions=['甲合同','乙劳动','丙租赁'].map(id=>h.session(id));
  for(const s of sessions)h.message(s,text(s.id));
  await tick();
  for(const s of sessions)h.message(s,text('后来上传的其他材料'));
  for(const s of [...sessions].reverse())pending.get(s.id)();
  await tick();
  assert.deepEqual(sessions.map(title),['甲合同摘要','乙劳动摘要','丙租赁摘要']);
  for(const s of sessions)h.message(s,text('再上传'));
  await tick();assert.equal(pending.size,3);
  assert.equal(sessions.reduce((n,s)=>n+s.events.filter(e=>e.type==='session/title').length,0),3);
  await h.close();
});
test('file-only first message is named and a manual rename wins an in-flight result',async()=>{
  let resolve;const h=harness(()=>new Promise(r=>resolve=r));const s=h.session('file');
  h.message(s,[{type:'file',attachment:{name:'材料.docx'}}]);await tick();
  assert.equal(typeof resolve,'function');
  h.emit(s,'session/title',{title:'律师自己命名',source:{kind:'user'}});
  resolve('自动名称');await tick();assert.equal(title(s),'律师自己命名');await h.close();
});
test('persisted name survives a new plugin lifetime; failures can only retry the first input',async()=>{
  let calls=0;const h=harness(async(s,first)=>{calls++;if(calls===1)throw Error('offline');return first.data.content[0].text});
  const s=h.session('retry');h.message(s,text('首次材料'));await tick();
  h.message(s,text('无关新材料'));await tick();assert.equal(title(s),'首次材料');
  const second=harness(async()=>{throw Error('must not generate again')});
  second.live.set(s.id,s);second.message(s,text('重开后上传'));await tick();assert.equal(title(s),'首次材料');
  await h.close();await second.close();
});
test('disposed conversations never receive a late title',async()=>{
  let finish;const h=harness(()=>new Promise(r=>finish=r));const s=h.session('removed');
  h.message(s,text('首份'));await tick();h.live.delete(s.id);finish('不能写入');await tick();
  assert.equal(title(s),undefined);await h.close();
});
test('input uses only its first event, reads attachment bodies, and bounds long Chinese input',async()=>{
  const attachments={fileHostPath: ref=>'/safe/'+ref.name,imageHostPath:ref=>'/safe/'+ref.name};
  const input=await titleInput({data:{content:[{type:'text',text:'请审查'},{type:'file',attachment:{name:'扫描件.docx'}}]}},attachments,
    async paths=>{assert.deepEqual(paths,['/safe/扫描件.docx']);return [{text:'虚构星河公司采购合同'}]});
  assert.match(input,/虚构星河公司采购合同/);
  const long=await titleInput({data:{content:text('中文材料'.repeat(20000))}},attachments,async()=>[]);
  assert.ok(Buffer.byteLength(long,'utf8')<=24000);assert.ok(!long.includes('\ufffd'));
});
test('a greeting title cannot lock out the first upload, and later uploads cannot replace it',async()=>{
  let calls=0;const h=harness(async(s,first)=>{calls++;return first.data.content[0].attachment?.name||'问候'});
  const s=h.session('greeting');h.message(s,text('你好'));await tick();assert.equal(title(s),'问候');
  h.message(s,[{type:'file',attachment:{name:'首次采购合同'}}]);await tick();assert.equal(title(s),'首次采购合同');
  h.message(s,[{type:'file',attachment:{name:'后来劳动材料'}}]);await tick();assert.equal(title(s),'首次采购合同');assert.equal(calls,2);
  await h.close();
});
test('first upload supersedes a pending greeting title without waiting for its response',async()=>{
  let greeting;const h=harness(async(s,first)=>{
    if(first.data.content[0].type==='text')return new Promise(resolve=>greeting=resolve);
    return '首次附件主题';
  });
  const s=h.session('race');h.message(s,text('你好'));await tick();
  h.message(s,[{type:'image',attachment:{name:'扫描件.png'}}]);await tick();assert.equal(title(s),'首次附件主题');
  greeting('过期问候');await tick();assert.equal(title(s),'首次附件主题');await h.close();
});
