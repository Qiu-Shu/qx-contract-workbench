import './content-watch-endurance/network-guard.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import net from 'node:net';
import {createContentWatch,INTERVAL_MS} from '../plugins/content-watch/core.mjs';
import {createFixture,profile} from './content-watch-endurance/fixture.mjs';
import {elapsed,observation} from './content-watch-endurance/timing.mjs';

test('a wall clock jump cannot complete 73 hours and a long host pause remains distinguishable',()=>{
  const start=1000,duration=262800000;
  assert.equal(elapsed(start,2000,duration).complete,false);
  assert.equal(observation(0,1000,262800000,2000).clockDiscontinuity,true);
  assert.equal(elapsed(start,262800999,duration).complete,false);
  assert.equal(elapsed(start,262801000,duration).complete,true);
  assert.deepEqual(observation(1000,1000,361000,361000),{wallGapMs:360000,monotonicGapMs:360000,clockDifferenceMs:0,hostGap:true,clockDiscontinuity:false});
  assert.equal(observation(10000,1000,0,2000).clockDiscontinuity,true);
});

test('the endurance guard rejects external fetch and raw sockets before network activity',()=>{
  assert.throws(()=>fetch('https://provider.invalid/'),/blocked/);
  assert.throws(()=>fetch('http://provider.invalid/'),/blocked/);
  assert.throws(()=>net.connect({host:'192.0.2.1',port:80}),/blocked/);
});

test('a second runner refuses an existing evidence directory and preserves its summary',async t=>{
  const directory=await mkdtemp(join(tmpdir(),'qx-endurance-existing-'));
  t.after(async()=>{assert.equal(dirname(directory),resolve(tmpdir()));await rm(directory,{recursive:true,force:true});});
  const bytes='{"status":"previous-run-must-remain"}\n';await writeFile(join(directory,'summary.json'),bytes);
  const runner=fileURLToPath(new URL('./content-watch-endurance/run.mjs',import.meta.url));
  const child=spawn(process.execPath,[runner,'--self-check',directory],{windowsHide:true,stdio:'ignore'});
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});
  assert.equal(code,1);assert.equal(await readFile(join(directory,'summary.json'),'utf8'),bytes);
});

async function fixture(t){
  const directory=await mkdtemp(join(tmpdir(),'qx-content-endurance-'));
  let at=Date.parse('2026-11-13T00:00:00Z');const clock=()=>at,transport=await createFixture(directory,{clock});
  const services=[];
  const open=async()=>{const service=await createContentWatch({stateDir:join(directory,'state'),client:transport.client,deliver:transport.deliver,clock});services.push(service);return service;};
  t.after(async()=>{for(const service of services)await service.dispose();await transport.close();assert.equal(dirname(directory),resolve(tmpdir()));await rm(directory,{recursive:true,force:true});});
  return {directory,transport,open,now:clock,setTime(value){at=value;}};
}

test('durable restart and ten missed cycles produce one current occurrence with persistent deduplication',async t=>{
  const f=await fixture(t),first=await f.open();await first.saveProfile(profile);await first.tick();
  assert.equal(INTERVAL_MS,259200000);const saved=first.status(),bytes=await readFile(saved.lastReport.path);
  assert.equal(saved.nextRunAt,Date.parse('2026-11-16T00:00:00Z'));await first.dispose();
  const reopened=await f.open();assert.equal(reopened.status().lastReport.id,saved.lastReport.id);
  f.setTime(saved.nextRunAt-1);await reopened.tick();assert.deepEqual(f.transport.counts(),{searches:4,details:1,summaries:1});
  f.transport.setGeneration(2);f.setTime(saved.nextRunAt+10*INTERVAL_MS);
  await Promise.all([reopened.tick(),reopened.tick()]);await reopened.tick();
  assert.deepEqual(f.transport.counts(),{searches:8,details:2,summaries:2});
  assert.deepEqual(reopened.status().lastReport.items.map(item=>item.id),['endurance-note-2']);
  assert.equal(reopened.status().nextRunAt,f.now()+259200000);
  await reopened.dispose();const third=await f.open();await third.run();
  assert.deepEqual(f.transport.counts(),{searches:12,details:2,summaries:2});
  assert.deepEqual(await readFile(saved.lastReport.path),bytes);f.transport.assertHealthy();
});

test('transport interruption blocks repeated scheduled attempts across restart and explicit recovery preserves old report',async t=>{
  const f=await fixture(t),service=await f.open();await service.saveProfile(profile);await service.tick();
  const old=service.status(),bytes=await readFile(old.lastReport.path);f.setTime(old.nextRunAt);f.transport.setGeneration(2);f.transport.setOutage(true);
  await service.tick();assert.equal(service.status().status,'provider_unavailable');const failedCount=f.transport.requests.length;
  await service.tick();await service.dispose();const reopened=await f.open();await reopened.tick();
  assert.equal(f.transport.requests.length,failedCount);assert.equal(reopened.status().lastReport.id,old.lastReport.id);
  f.transport.setOutage(false);await reopened.resume();await reopened.tick();
  assert.equal(reopened.status().status,'ready');assert.equal(f.transport.receipts.length,2);
  assert.deepEqual(reopened.status().lastReport.items.map(item=>item.id),['endurance-note-2']);assert.deepEqual(await readFile(old.lastReport.path),bytes);
  f.transport.assertHealthy();
});

for(const phase of ['submitted','unsubmitted'])test('actual process termination at '+phase+' boundary recovers without duplicate submission',async t=>{
  const stateDir=await mkdtemp(join(tmpdir(),'qx-content-crash-'));
  const worker=fileURLToPath(new URL('./content-watch-endurance/crash-worker.mjs',import.meta.url));
  const child=spawn(process.execPath,[worker,stateDir,phase],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  t.after(async()=>{if(child.exitCode===null&&child.signalCode===null)child.kill();assert.equal(dirname(stateDir),resolve(tmpdir()));await rm(stateDir,{recursive:true,force:true,maxRetries:3});});
  await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('crash worker timeout: '+output)),15000);
    child.on('error',error=>{clearTimeout(timer);reject(error);});child.on('exit',code=>{clearTimeout(timer);reject(Error('worker exited early '+code+': '+output));});
    child.stderr.on('data',data=>{output+=data;});child.stdout.on('data',data=>{output+=data;if(output.includes('CRASH_BOUNDARY_READY')){clearTimeout(timer);resolve();}});
  });
  const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGKILL');await exited;
  let collections=0,deliveries=0;
  const service=await createContentWatch({stateDir,client:{checkLogin:async()=>({loggedIn:true}),collect:async()=>{collections++;return {items:[{id:'crash-note',title:'合成中断样本'}]};}},deliver:async report=>{deliveries++;await report.onSubmitting({messageId:'recovered'});return {content:'合成恢复摘要'};}});
  t.after(()=>service.dispose());assert.equal(service.status().enabled,false);assert.equal(service.status().status,'error');
  const report=service.status().lastReport;assert.equal(report.submitted,phase==='submitted');await service.tick();assert.equal(collections,0);assert.equal(deliveries,0);
  await service.resume();await service.tick();
  assert.equal(service.status().lastReport.id,report.id);
  assert.equal(deliveries,phase==='submitted'?0:1);assert.equal(collections,phase==='submitted'?1:0);
  if(phase==='submitted')assert.equal((await readFile(join(stateDir,'accepted.jsonl'),'utf8')).trim().split('\n').length,1);
});
