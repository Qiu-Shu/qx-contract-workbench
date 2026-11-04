const {test}=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createSupervisor,createHostMonitor,createEventLog}=require('./host-recovery.cjs');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn){for(let i=0;i<200;i++){if(fn())return;await delay(10)}assert.fail('Timed out');}

test('real crashed children restart three times, then wait; exit code is recorded',async()=>{
  let launches=0;const events=[],states=[];
  const supervisor=createSupervisor({start:()=>{launches++;return spawn(process.execPath,['-e','process.exit(7)'],{stdio:'ignore',windowsHide:true})},
    onState:s=>states.push(s),log:(event,fields)=>events.push({event,...fields}),delays:[5,5,5]});
  supervisor.start();await until(()=>states.at(-1)?.phase==='failed');
  assert.equal(launches,4);assert.equal(events.filter(e=>e.event==='child_exit'&&e.code===7).length,4);
  await delay(30);assert.equal(launches,4);supervisor.stop();
});

test('intentional stop cancels a pending recovery and does not restart',async()=>{
  const child=new EventEmitter();child.pid=123;let count=0,stops=0;
  const supervisor=createSupervisor({start:()=>{count++;return child},kill:()=>stops++,delays:[30,30,30]});
  supervisor.start();child.emit('close',1,null);supervisor.stop();await delay(60);
  assert.equal(count,1);assert.equal(stops,0);
});

test('stop during live child exit is intentional, and repeated error/close schedules once',async()=>{
  let count=0;const children=[],events=[];
  const supervisor=createSupervisor({start:()=>{const child=new EventEmitter();child.pid=++count;children.push(child);return child},
    kill:child=>child.emit('close',null,'SIGTERM'),log:(event,fields)=>events.push({event,...fields}),delays:[5]});
  supervisor.start();children[0].emit('error',Object.assign(Error('secret'),{code:'ENOENT'}));children[0].emit('close',-2,null);
  await until(()=>count===2);supervisor.stop();await delay(20);
  assert.equal(count,2);assert.equal(events.at(-1).event,'child_exit');assert.equal(events.at(-1).intentional,true);
});

test('desktop restores a dead launcher once, keeps UI pending explicit reconnect and never replays input',async()=>{
  let host={runtime:null,control:null,state:null},recoveries=0;
  const states=[];const monitor=createHostMonitor({probe:async()=>host,recover:async()=>{recoveries++;host={runtime:{url:'http://127.0.0.1:123/?token=test'},control:{}}},onState:s=>states.push(s)});
  await Promise.all([monitor.tick(),monitor.tick(),monitor.tick()]);await monitor.tick();
  assert.equal(recoveries,1);assert.equal(monitor.state().phase,'ready');
  monitor.connected();assert.equal(monitor.state().phase,'connected');
  assert.ok(!JSON.stringify(states).includes('token='));
});

test('desktop never revives intentionally stopped service, busy settings/install, or live unresponsive host',async()=>{
  let calls=0,paused=true;
  let host={runtime:null,control:null,state:null};
  const monitor=createHostMonitor({probe:async()=>host,recover:async()=>calls++,isPaused:()=>paused});
  await monitor.tick();paused=false;host.state={phase:'stopped'};await monitor.tick();assert.equal(monitor.state().phase,'stopped');
  host={runtime:null,control:{},state:{phase:'running'}};await monitor.tick();assert.equal(monitor.state().phase,'disconnected');
  assert.equal(calls,0);
});

test('desktop recovery budget is bounded and checks pause again after pending health check',async()=>{
  let calls=0,paused=false,resolve;
  const monitor=createHostMonitor({probe:async()=>({}),recover:async()=>{calls++;throw Error('private')},maxAttempts:3});
  for(let i=0;i<8;i++)await monitor.tick();
  assert.equal(calls,3);assert.equal(monitor.state().phase,'failed');
  const pending=createHostMonitor({probe:()=>new Promise(r=>resolve=r),recover:async()=>calls++,isPaused:()=>paused});
  const tick=pending.tick();paused=true;resolve({});await tick;assert.equal(calls,3);
});

test('event log stores only safe fields and rotates bounded files',()=>{
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'qx-event-test-'));
  try{
    const log=createEventLog(data,'host',{maxBytes:300});
    for(let i=0;i<12;i++)log('child_exit',{code:7,signal:null,intentional:false,attempt:i,secret:'NEVER_WRITE',message:'NEVER_WRITE',url:'NEVER_WRITE'});
    const dir=path.join(data,'.local');const names=fs.readdirSync(dir);
    assert.deepEqual(names.sort(),['host-events.jsonl','host-events.jsonl.1']);
    for(const name of names){const text=fs.readFileSync(path.join(dir,name),'utf8');assert.doesNotMatch(text,/NEVER_WRITE/);for(const line of text.trim().split('\n'))assert.equal(JSON.parse(line).code,7);assert.ok(text.length<600);}
  }finally{fs.rmSync(data,{recursive:true,force:true})}
});

test('fast recovery between polls still asks the old window to reconnect',async()=>{
  let runtime={url:'http://127.0.0.1:1/?token=first',hostPid:101,launcherPid:100};
  const monitor=createHostMonitor({probe:async()=>({runtime}),recover:async()=>assert.fail('already healthy')});
  monitor.connected(runtime);await monitor.tick();
  runtime={...runtime,url:'http://127.0.0.1:1/?token=second',hostPid:102};await monitor.tick();
  assert.equal(monitor.state().phase,'ready');
  monitor.connected(runtime);await monitor.tick();assert.equal(monitor.state().phase,'connected');
});

test('starting child PID is published before readiness to prevent orphan duplication',()=>{
  const states=[],child=new EventEmitter();child.pid=1234;
  const supervisor=createSupervisor({start:()=>child,onState:s=>states.push(s),kill:()=>child.emit('close',0,null)});
  supervisor.start();const starting=states.at(-1);supervisor.stop();
  assert.equal(starting.phase,'starting');assert.equal(starting.hostPid,1234);
});
