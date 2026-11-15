import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {Readable} from 'node:stream';
import {mkdtemp,mkdir,readFile,writeFile,readdir,realpath,rename,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {apply} from '../index.js';

const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};};
const tick=()=>new Promise(r=>setTimeout(r,15));
async function until(fn){for(let n=0;n<100;n++){if(await fn())return;await tick();}throw Error('condition timed out');}
function event(id,text='虚构合同',extra={}) {return {header:{app_id:'cli_synthetic',event_type:'im.message.receive_v1',event_id:'event-'+id},event:{sender:{sender_type:'user',sender_id:{open_id:'ou_owner'},tenant_key:'tenant-synthetic'},message:{message_id:id,chat_id:'oc_owner',chat_type:'p2p',create_time:String(Date.now()),message_type:'text',content:JSON.stringify({text}),...extra}}};}
async function fixture(t,{root,now=()=>Date.now(),download,replyGate,sendText,fetchDocument,secretFail=false,realProtector=false,connectionStart,connectionTimeoutMs=1000,autoConnect}={}){
  root??=await mkdtemp(join(tmpdir(),'qx-feishu-test-'));const workspace=join(root,'workspace'),stateDir=join(root,'state');await mkdir(workspace,{recursive:true});
  const bus=new EventEmitter(),routes=new Map(),tools=new Map(),cleanup=[],sent=[],followups=[],connections=[];let turns=0;
  const rows=[{sessionId:'current',cwd:workspace,projections:{values:{title:'当前虚构会话'}}},{sessionId:'second',cwd:workspace},{sessionId:'foreign',cwd:join(root,'foreign')},{sessionId:'archived',cwd:workspace}];
  const agents=new Map(['current','second','foreign','archived'].map(id=>[id,{session:{id},whenIdle:async()=>{},followup(message){followups.push({id,message});const turn=++turns;bus.emit('agent/inbox/claimed',{agent:this,message,turn});void(async()=>{await replyGate?.promise;bus.emit('session/event',{id},{type:'assistant/message',data:{turn,message:{content:[{type:'text',text:'虚构分析答复'}]}}});bus.emit('session/event',{id},{type:'turn/end',data:{turn,reason:{kind:'end_turn'}}});})();}}]));
  const registry={archivedSessionIds:new Set(['archived'])};
  const services={sessionController:{list:async()=>({items:rows})},workspaceRegistry:registry,workingDirectory:{ensure:async agent=>rows.find(row=>row.sessionId===agent.session.id)?.cwd}};
  const ctx={on:bus.on.bind(bus),agents:{get:id=>agents.get(id)},get:key=>services[key],workingDirectory:services.workingDirectory,
    loader:{internal:{import:async name=>{if(name==='@deepseek-ai/dsh-llm')return{createUserMessage:value=>({id:'user-'+(turns+1),...value})};throw Error('unexpected import '+name);}}},
    effect(fn){const stop=fn();if(typeof stop==='function')cleanup.push(stop);},inject(deps,fn){fn({...ctx,tools:{register:tool=>{tools.set(tool.name,tool);return()=>tools.delete(tool.name);}},webServer:{register:route=>{routes.set(route.path,route.handler);return()=>routes.delete(route.path);}}});}};
  const transportFactory=credentials=>({verify:async()=>{},connection:()=>{const connection={handler:null,connected:false,onEvent(fn){this.handler=fn;},onError(){},async start(){await connectionStart?.();this.connected=true;},stop(){this.connected=false;},status(){return{connected:this.connected};}};connections.push(connection);return connection;},
    download:download??(async()=>({bytes:Buffer.from('synthetic attachment'),contentType:'application/pdf'})),
    sendText:async value=>{sent.push({...value,appId:credentials.appId});return sendText?.(value);},upload:async()=>({fileKey:'file-synthetic'}),sendFile:async value=>sent.push({...value,appId:credentials.appId}),
    readDocument:fetchDocument??(async url=>({source:url,content:'虚构正文'.repeat(5000),fetchedAt:'2026-11-15T00:00:00.000Z'}))});
  await apply(ctx,{workspace,stateDir,coalesceQuietMs:1,coalesceMediaQuietMs:1,replyTimeoutMs:1000,connectionTimeoutMs,autoConnect},{transportFactory,now,...(realProtector?{}:{protector:{available:true,protect:async value=>{if(secretFail)throw Error('synthetic-secret');return Buffer.from(value).toString('base64');},reveal:async value=>Buffer.from(value,'base64').toString()}})});
  async function request(path,{method='GET',body,headers={},remote='127.0.0.1'}={}){const req=Readable.from(body===undefined?[]:[typeof body==='string'?body:JSON.stringify(body)]);Object.assign(req,{method,headers:{host:'127.0.0.1:3333',...headers},socket:{remoteAddress:remote}});let result;await routes.get('/qx-feishu/'+path)(req,{writeHead(status){this.status=status;},end(text){result={status:this.status,data:JSON.parse(text)};}});return result;}
  const csrf=(await request('settings')).data.csrf;
  const action=body=>request('action',{method:'POST',body,headers:{'x-qx-token':csrf,origin:'http://127.0.0.1:3333'}});
  const state=async()=>(await request('state')).data;
  async function connect(){const result=await action({action:'connect',appId:'cli_synthetic',appSecret:'synthetic-secret',sessionId:'current'});assert.equal(result.status,200,JSON.stringify(result));}
  const receive=value=>connections.at(-1).handler(value);
  async function pair(){const {pairing}=await state();assert.ok(pairing);await receive(event('pair-'+pairing.code,'连接 '+pairing.code));await tick();}
  async function close(){for(const stop of cleanup.splice(0))await stop();}
  t.after(async()=>{await close();await rm(root,{recursive:true,force:true});});
  return{root,workspace,stateDir,ctx,agents,rows,registry,request,action,state,connect,receive,pair,sent,followups,connections,tools,close};
}
test('unconfigured is offline; routes enforce loopback origin, methods, CSRF and request limits',async t=>{
  const f=await fixture(t);assert.equal((await f.state()).configured,false);assert.equal(f.connections.length,0);
  assert.equal((await f.request('state',{method:'POST'})).status,405);
  assert.equal((await f.request('settings',{headers:{origin:'https://evil.test'}})).status,403);
  assert.equal((await f.request('settings',{headers:{host:'evil.test'}})).status,403);
  assert.equal((await f.request('settings',{headers:{'sec-fetch-site':'cross-site'}})).status,403);
  assert.equal((await f.request('state',{remote:'192.0.2.1'})).status,403);
  assert.equal((await f.request('action',{method:'POST',body:{action:'connect'}})).status,403);
  assert.equal((await f.action('x'.repeat(9000))).status,413);
  const list=(await f.request('settings')).data.sessions;assert.deepEqual(list.map(row=>row.id),['current','second']);
});
test('connect seals credentials, issues one-time short pairing, rejects groups and strangers',async t=>{
  const f=await fixture(t);await f.connect();let state=await f.state();assert.equal(state.owner,null);assert.ok(state.pairing.code);
  assert.ok(!JSON.stringify(state).includes('synthetic-secret'));
  const stored=await readFile(join(f.stateDir,'settings.json'),'utf8');assert.ok(!stored.includes('synthetic-secret'));assert.match(stored,/dpapi:/);
  await f.receive(event('group','连接 '+state.pairing.code,{chat_type:'group'}));assert.equal((await f.state()).owner,null);
  await f.receive(event('wrong','hello'));assert.equal((await f.state()).owner,null);
  await f.pair();assert.equal((await f.state()).owner,'ou_owner');assert.equal((await f.state()).pairing,null);
  const stranger=event('stranger');stranger.event.sender.sender_id.open_id='ou_stranger';await f.receive(stranger);assert.equal(f.followups.length,0);
  await f.receive(event('one'));await until(()=>f.followups.length===1);await until(()=>f.sent.length>=1);
  assert.equal(f.followups[0].id,'current');assert.match(f.followups[0].message.content[0].text,/虚构合同/);
  assert.ok(f.sent.every(row=>row.owner==='ou_owner'));
});
test('expired pairing and failed secret protection never bind or write plaintext',async t=>{
  let clock=1000;const f=await fixture(t,{now:()=>clock});await f.connect();const code=(await f.state()).pairing.code;clock+=301000;
  await f.receive(event('expired','连接 '+code));assert.equal((await f.state()).owner,null);
  assert.equal((await f.action({action:'connect',appId:'cli_other',appSecret:'x',sessionId:'foreign'})).status,400);
  const bad=await fixture(t,{secretFail:true});const result=await bad.action({action:'connect',appId:'cli_synthetic',appSecret:'synthetic-secret',sessionId:'current'});assert.equal(result.status,400);assert.ok(!JSON.stringify(result).includes('synthetic-secret'));assert.equal((await bad.state()).configured,false);
});
test('event dedup is durable across restart and pending work is quarantined, never replayed',async t=>{
  const f=await fixture(t);await f.connect();await f.pair();await f.receive(event('once'));await until(()=>f.followups.length===1);await until(async()=>!(await f.state()).batching.active);
  await f.receive(event('once'));assert.equal(f.followups.length,1);
  await f.receive(event('held','还没发完'));await f.close();
  const restarted=await fixture(t,{root:f.root});await until(()=>restarted.connections.length===1);
  await restarted.receive(event('once'));await restarted.receive(event('held','还没发完'));assert.equal(restarted.followups.length,0);
  const inbox=JSON.parse(await readFile(join(f.stateDir,'inbox.json'),'utf8'));assert.ok(inbox.failed.some(batch=>batch.status==='interrupted'));
});
test('download and active reply prevent switching; paused late content does not reach another session',async t=>{
  const gate=deferred();const f=await fixture(t,{download:async()=>{await gate.promise;return{bytes:Buffer.from('synthetic'),contentType:'application/pdf'};}});await f.connect();await f.pair();
  const receiving=f.receive(event('file','',{message_type:'file',content:JSON.stringify({file_key:'file_synthetic',file_name:'../../bad\r\n.pdf'})}));await tick();
  assert.equal((await f.action({action:'session',sessionId:'second'})).status,400);
  await f.action({action:'pause'});gate.resolve();await receiving;assert.equal(f.followups.length,0);
  assert.equal((await f.state()).paused,true);
  assert.ok(JSON.parse(await readFile(join(f.stateDir,'inbox.json'),'utf8')).failed.length>0);
});
test('late model response after pause is suppressed and never sent by the next binding',async t=>{
  const replyGate=deferred();const f=await fixture(t,{replyGate});await f.connect();await f.pair();await f.receive(event('delayed'));await until(()=>f.followups.length===1);
  const before=f.sent.length;assert.equal((await f.action({action:'session',sessionId:'second'})).status,400);await f.action({action:'pause'});replyGate.resolve();await until(async()=>!(await f.state()).batching.active);assert.equal(f.sent.length,before);
  assert.equal((await f.action({action:'session',sessionId:'second'})).status,200);await f.action({action:'resume'});await tick();assert.equal(f.sent.length,before);
});
test('attachments persist inside workspace, and failed downloads stay explicit without fabricated content',async t=>{
  const f=await fixture(t,{download:async()=>{throw Error('secret=synthetic-secret');}});await f.connect();await f.pair();await f.receive(event('bad-file','',{message_type:'file',content:JSON.stringify({file_key:'file_synthetic',file_name:'contract.pdf'})}));
  await until(async()=>!(await f.state()).batching.active&&(await f.state()).batching.pendingMessages===0);assert.equal(f.followups.length,0);
  const inbox=await readFile(join(f.stateDir,'inbox.json'),'utf8');assert.ok(!inbox.includes('synthetic-secret'));assert.match(inbox,/failed/);
});
test('tools validate live host session; read allows same workspace, send requires bound session and local path',async t=>{
  const f=await fixture(t);await f.connect();await f.pair();const read=f.tools.get('feishu_read_document'),send=f.tools.get('feishu_send_file');
  const exec=id=>({agent:f.agents.get(id),signal:new AbortController().signal});
  await assert.rejects(()=>read.execute({url:'https://synthetic.feishu.cn/docx/Doc123'},{}),/会话/);
  await assert.rejects(()=>read.execute({url:'https://synthetic.feishu.cn/docx/Doc123'},exec('foreign')),/工作区|会话/);
  await assert.rejects(()=>read.execute({url:'https://synthetic.feishu.cn/docx/Doc123'},exec('archived')),/会话/);
  const first=JSON.parse(await read.execute({url:'https://synthetic.feishu.cn/docx/Doc123'},exec('second')));assert.equal(first.offset,0);assert.ok(first.nextOffset>0);assert.equal(first.source,'https://synthetic.feishu.cn/docx/Doc123');
  await assert.rejects(()=>send.execute({path:join(f.workspace,'out.txt')},exec('second')),/绑定/);
  await assert.rejects(()=>send.execute({path:join(f.root,'outside.txt')},exec('current')),/工作区/);
  await writeFile(join(f.workspace,'out.txt'),'synthetic output');const result=await send.execute({path:join(f.workspace,'out.txt')},exec('current'));assert.match(result,/本人飞书/);assert.equal(f.sent.at(-1).owner,'ou_owner');
});
test('file success keeps sanitized artifact in existing workspace and forwards its actual path',async t=>{
  const f=await fixture(t);await f.connect();await f.pair();await f.receive(event('good-file','',{message_type:'file',content:JSON.stringify({file_key:'file_synthetic',file_name:'../../CON\r\n.pdf'})}));
  await until(()=>f.followups.length===1);await until(async()=>!(await f.state()).batching.active);
  const names=await readdir(join(f.workspace,'feishu-inbox'));assert.equal(names.length,1);assert.ok(!/[\r\n\/\\]/.test(names[0]));
  assert.equal(await readFile(join(f.workspace,'feishu-inbox',names[0]),'utf8'),'synthetic attachment');assert.ok(f.followups[0].message.content[0].text.includes(await realpath(join(f.workspace,'feishu-inbox',names[0]))));
});
test('failed or unknown send result is not retried on redelivery or restart',async t=>{
  const f=await fixture(t,{sendText:async()=>{throw Error('provider echo synthetic-secret');}});await f.connect();await f.pair();await f.receive(event('send-unknown'));await until(()=>f.sent.length===1);await until(async()=>!(await f.state()).batching.active);
  assert.ok(!(await f.state()).lastError.includes('synthetic-secret'));await f.receive(event('send-unknown'));assert.equal(f.sent.length,1);await f.close();
  const restarted=await fixture(t,{root:f.root});await restarted.receive(event('send-unknown'));await tick();assert.equal(restarted.sent.length,0);
});
test('concurrent settings requests are excluded and a stalled connection has a bounded failure',{timeout:2000},async t=>{
  const gate=deferred();const f=await fixture(t,{connectionStart:()=>gate.promise,connectionTimeoutMs:30});
  const opening=f.action({action:'connect',appId:'cli_synthetic',appSecret:'synthetic-secret',sessionId:'current'});await until(()=>f.connections.length===1);
  assert.equal((await f.action({action:'clear'})).status,409);const outcome=await opening;assert.equal(outcome.status,400);assert.match(outcome.data.error,/超时/);gate.resolve();await tick();assert.equal((await f.state()).connected,false);
});
test('incoming work revalidates the live working directory before forwarding',async t=>{
  const f=await fixture(t);await f.connect();await f.pair();f.ctx.workingDirectory.ensure=async()=>join(f.root,'foreign');await f.receive(event('changed-cwd'));await until(async()=>!(await f.state()).batching.active&&(await f.state()).batching.pendingMessages===0);assert.equal(f.followups.length,0);
});
test('old connection events cannot enter after application change',async t=>{
  const f=await fixture(t);await f.connect();await f.pair();const old=f.connections[0];await f.action({action:'clear'});await f.connect();await old.handler(event('old-late'));assert.equal((await f.state()).owner,null);assert.equal((await f.state()).batching.pendingMessages,0);
});
test('Windows DPAPI protects synthetic credentials and decrypts after restart',{skip:process.platform!=='win32'},async t=>{
  const f=await fixture(t,{realProtector:true});await f.connect();await f.pair();const stored=JSON.parse(await readFile(join(f.stateDir,'settings.json'),'utf8'));assert.ok(stored.feishu.appSecret.startsWith('dpapi:'));assert.notEqual(stored.feishu.appSecret,'dpapi:'+Buffer.from('synthetic-secret').toString('base64'));await f.close();
  const restarted=await fixture(t,{root:f.root,realProtector:true});assert.equal((await restarted.state()).configured,true);assert.equal((await restarted.state()).owner,'ou_owner');
});
test('portable autoConnect false prevents reconnect even with old settings retained',async t=>{
  const f=await fixture(t);await f.connect();await f.pair();await f.close();const restored=await fixture(t,{root:f.root,autoConnect:false});assert.equal(restored.connections.length,0);assert.equal((await restored.state()).paused,true);
});
test('message sent before binding switch but delivered afterward is quarantined',async t=>{
  let clock=100000;const f=await fixture(t,{now:()=>clock});await f.connect();await f.pair();clock+=1000;
  assert.equal((await f.action({action:'session',sessionId:'second'})).status,200);
  await f.receive(event('server-late','旧会话的虚构材料',{create_time:'100500'}));await tick();assert.equal(f.followups.length,0);
  assert.ok(JSON.parse(await readFile(join(f.stateDir,'inbox.json'),'utf8')).failed.some(batch=>batch.items.some(item=>item.id.endsWith(':server-late'))));
  await f.receive(event('new-binding','新会话虚构材料',{create_time:'101001'}));await until(()=>f.followups.length===1);assert.equal(f.followups[0].id,'second');
});
test('reply rechecks live workspace after model execution',async t=>{
  const replyGate=deferred();const f=await fixture(t,{replyGate});await f.connect();await f.pair();await f.receive(event('reply-cwd'));await until(()=>f.followups.length===1);
  f.ctx.workingDirectory.ensure=async()=>join(f.root,'foreign');replyGate.resolve();await until(async()=>!(await f.state()).batching.active);assert.equal(f.sent.length,0);
});
for(const action of ['session','connect','clear','pair-owner'])test(`${action} persistence failure never publishes a new binding`,async t=>{
  const f=await fixture(t);await f.connect();if(action!=='pair-owner')await f.pair();const before=await f.state();
  const path=join(f.stateDir,'settings.json'),backup=path+'.original';await rename(path,backup);await mkdir(path);
  try{
    if(action==='pair-owner')await assert.rejects(()=>f.receive(event('pair-failure','连接 '+before.pairing.code)));
    else assert.equal((await f.action(action==='session'?{action,sessionId:'second'}:action==='connect'?{action,appId:'cli_other',appSecret:'other-synthetic-secret',sessionId:'second'}:{action})).status,400);
    const after=await f.state();assert.equal(after.sessionId,before.sessionId);assert.equal(after.appId,before.appId);assert.equal(after.owner,before.owner);assert.equal(after.configured,before.configured);
  }finally{await rm(path,{recursive:true});await rename(backup,path);}
});
test('server redelivery from before resume or restart is retained without forwarding',async t=>{
  let clock=100000;const f=await fixture(t,{now:()=>clock});await f.connect();await f.pair();await f.action({action:'pause'});clock=200000;await f.action({action:'resume'});
  await f.receive(event('pre-resume','暂停时发送的材料',{create_time:'150000'}));await tick();assert.equal(f.followups.length,0);
  await f.close();clock=300000;const restarted=await fixture(t,{root:f.root,now:()=>clock});await restarted.receive(event('pre-restart','重启前材料',{create_time:'250000'}));await tick();assert.equal(restarted.followups.length,0);
});
test('pause stays durable when owner pairing is being persisted concurrently',async t=>{
  const f=await fixture(t);await f.connect();const code=(await f.state()).pairing.code;
  const receiving=f.receive(event('pair-overlap','连接 '+code));const pausing=f.action({action:'pause'});await Promise.all([receiving,pausing]);
  assert.equal((await f.state()).paused,true);assert.equal(JSON.parse(await readFile(join(f.stateDir,'settings.json'),'utf8')).paused,true);
});
