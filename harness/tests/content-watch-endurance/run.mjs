// Bounded real-clock check. Production scheduling stays at 72h / 60s / 30s.
// Real content-watch lifecycle, parser, timers and disk state; only remote collection
// and summary admission are synthetic local HTTP boundaries, not a full DSH agent.
import {rejected} from './network-guard.mjs';
import assert from 'node:assert/strict';
import {appendFile,mkdir,readFile,writeFile,rename,readdir,open,unlink} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {dirname,join,resolve,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {installContentWatch} from '../../plugins/content-watch/index.mjs';
import {INTERVAL_MS} from '../../plugins/content-watch/core.mjs';
import {createFixture,profile} from './fixture.mjs';
import {elapsed,observation} from './timing.mjs';

const here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../..');
const args=process.argv.slice(2),mode=args[0],directory=args[1]&&resolve(args[1]);
assert.ok(['--run','--self-check','--inspect'].includes(mode)&&directory&&isAbsolute(args[1])&&args.length===2,
  'Usage: node tests/content-watch-endurance/run.mjs --run|--self-check|--inspect <absolute evidence directory>');
const summaryPath=join(directory,'summary.json'),journalPath=join(directory,'events.jsonl');
if(mode==='--inspect'){
  const summary=JSON.parse(await readFile(summaryPath,'utf8'));
  let alive=false;try{process.kill(summary.pid,0);alive=true;}catch{}
  const ageMs=Date.now()-Date.parse(summary.updatedAt);
  console.log(JSON.stringify({...summary,processAlive:alive,processIdentityVerified:false,evidenceAgeMs:ageMs,
    observation:summary.status==='running'&&!alive?'interrupted: process no longer exists; no completion claim':summary.status==='running'&&ageMs>3700000?'heartbeat overdue: inspect host sleep or process health':summary.status==='running'?'PID exists, identity not verified: inspect executable, command line and creation time':summary.status},null,2));
}else await run();

async function sourceHashes(){
  const paths=['plugins/content-watch','tests/content-watch-endurance'];const files=[];
  for(const base of paths)for(const name of await readdir(join(root,base)))if(name.endsWith('.mjs')&&!name.endsWith('.test.mjs'))files.push(join(base,name));
  files.push('plugins/wechat/session.js','scripts/prepare-content-watch.mjs');
  const hashes={};for(const file of files.sort())hashes[file.replaceAll('\\','/')]=createHash('sha256').update(await readFile(join(root,file))).digest('hex');
  return hashes;
}
async function run(){
  const selfCheck=mode==='--self-check',durationMs=selfCheck?80000:73*3600000;
  await mkdir(dirname(directory),{recursive:true});await mkdir(directory);
  // Exclusive marker and immutable manifest prevent accidentally reusing another run's evidence.
  const marker=await open(join(directory,'runner.lock'),'wx');await marker.writeFile(String(process.pid));
  let watcher,transport,stopReason=null;const stateDir=join(directory,'state');
  const startedAt=Date.now(),startedMono=performance.now(),deadline=startedAt+durationMs;
  const report={version:1,status:'running',mode:selfCheck?'short-self-check':'real-clock-73-hours',pid:process.pid,
    startedAt:new Date(startedAt).toISOString(),startedDeadline:new Date(deadline).toISOString(),durationMs,
    productionIntervalMs:INTERVAL_MS,productionInitialTimerMs:30000,productionPollTimerMs:60000,
    sourceRoot:root,node:process.version,nodeExecutable:process.execPath,
    scope:'real content-watch installation, timer, parser and durable reports; synthetic loopback collection/summary; no real DSH model or account',
    realProviderRequests:0,realAccountsRead:0,checks:[],hostGaps:[],clockDiscontinuities:[],heartbeats:0,continuousObservation:true,threeDayVerificationComplete:false};
  const stop=signal=>{stopReason=signal;};
  process.once('SIGINT',stop);process.once('SIGTERM',stop);
  const event=async(kind,details={})=>{
    const entry={at:new Date().toISOString(),kind,...details};await appendFile(journalPath,JSON.stringify(entry)+'\n');
    console.log(JSON.stringify(entry));
  };
  const save=async()=>{
    report.updatedAt=new Date().toISOString();report.counts=transport?.counts();report.networkDenials=rejected.length;
    report.memory=process.memoryUsage();
    const temporary=summaryPath+'.tmp';await writeFile(temporary,JSON.stringify(report,null,2)+'\n');await rename(temporary,summaryPath);
  };
  const check=async(name,details={})=>{report.checks.push({name,...details});await event('check',{name,...details});await save();};
  let first,second,restarted=false,previousWall=Date.now(),previousMono=performance.now(),nextHeartbeat=startedAt+3600000;
  let peakRss=process.memoryUsage().rss,peakHeap=process.memoryUsage().heapUsed;
  const install=async()=>{
    const routes=new Map(),ctx={connection:{fetch:{register:route=>routes.set(route.path,route)}},effect(){}};
    watcher=await installContentWatch(ctx,{workspace:join(directory,'synthetic-workspace'),stateDir},{
      client:transport.client,connectionStore:{status:()=>({provider:'justone',tokenConfigured:true}),token:()=> 'endurance-synthetic-only'},
      runtime:{ensureStarted:async()=>{throw Error('Synthetic run must never start a local account runtime');},stop:async()=>{}},
      sessionDelivery:{prepare:async()=>{},deliver:transport.deliver,dispose(){},draft:async()=>{throw Error('No drafts in endurance fixture');}},
    });
    return async(endpoint,data)=>{
      const route=routes.get('/api/qx-content-watch/'+endpoint);
      const response=await route.fetch(new Request('http://127.0.0.1/api/qx-content-watch/'+endpoint,{method:data?'POST':'GET',
        headers:{'x-qx-content-watch':'1','content-type':'application/json'},...(data?{body:JSON.stringify(data)}:{})}));
      assert.ok(response.ok,'content route rejected '+endpoint);return response.json();
    };
  };
  try{
    assert.equal(INTERVAL_MS,259200000);assert.ok(resolve(directory)!==root&&!directory.startsWith(root+'\\'),'Keep evidence outside source');
    report.sourceHashes=await sourceHashes();report.nodeSha256=createHash('sha256').update(await readFile(process.execPath)).digest('hex');
    await writeFile(join(directory,'manifest.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
    transport=await createFixture(directory);let api=await install();await api('profile',profile);
    report.initialDueAt=new Date(watcher.status().nextRunAt).toISOString();
    await event('started',{pid:process.pid,mode:report.mode,deadline:report.startedDeadline,initialDueAt:report.initialDueAt,productionIntervalMs:INTERVAL_MS});await save();
    while(!elapsed(startedMono,performance.now(),durationMs).complete&&!stopReason){
      await delay(selfCheck?250:10000);
      const wall=Date.now(),mono=performance.now(),observed=observation(previousWall,previousMono,wall,mono);
      if(observed.hostGap||observed.clockDiscontinuity){
        const gap={observedAt:new Date(wall).toISOString(),...observed,
          classification:'host suspension, clock change or scheduler stall suspected; cause is not proven'};
        report.hostGaps.push(gap);report.continuousObservation=false;await event('host-gap',gap);await save();
        if(observed.clockDiscontinuity){report.clockDiscontinuities.push(gap);await event('clock-discontinuity',gap);}
      }
      previousWall=wall;previousMono=mono;
      const memory=process.memoryUsage();peakRss=Math.max(peakRss,memory.rss);peakHeap=Math.max(peakHeap,memory.heapUsed);
      report.peakMemory={rss:peakRss,heapUsed:peakHeap};
      const state=watcher.status();
      assert.ok(['ready','running'].includes(state.status),'content task failed: '+state.status);
      if(state.status==='ready'&&state.lastRunAt&&!first){
        first=structuredClone(state);assert.ok(first.lastRunAt>=startedAt+29000,'Initial run must use production startup timer');
        assert.equal(transport.receipts.length,1);assert.deepEqual(transport.counts(),{searches:4,details:1,summaries:1});assert.equal(first.lastReport.submitted,true);assert.equal(first.lastReport.pending,false);
        assert.ok(first.nextRunAt-first.lastRunAt>=259200000&&first.nextRunAt-first.lastRunAt<259201000);
        report.firstScheduled={actualAt:new Date(first.lastRunAt).toISOString(),nextDueAt:new Date(first.nextRunAt).toISOString(),reportId:first.lastReport.id};
        report.firstReportSha256=createHash('sha256').update(await readFile(first.lastReport.path)).digest('hex');
        if(!selfCheck)transport.setGeneration(2);
        await check('first occurrence ran on unchanged production startup timer',report.firstScheduled);
      }
      if(first&&!restarted&&wall>=first.lastRunAt+(selfCheck?2000:3600000)){
        await watcher.dispose();api=await install();restarted=true;report.restartedAt=new Date().toISOString();
        assert.equal(watcher.status().lastReport.id,first.lastReport.id);assert.equal(watcher.status().nextRunAt,first.nextRunAt);
        await check('service disposed and reopened durable state without changing its due time',{nextDueAt:report.firstScheduled.nextDueAt});
      }
      if(first&&state.lastRunAt>first.lastRunAt&&!second){
        assert.ok(!selfCheck,'Short self-check must not have another scheduled occurrence');
        assert.ok(state.lastRunAt>=first.nextRunAt,'Periodic run must not happen early');
        second=structuredClone(state);assert.equal(transport.receipts.length,2);
        assert.deepEqual(transport.counts(),{searches:8,details:2,summaries:2});
        assert.ok(second.nextRunAt-second.lastRunAt>=259200000&&second.nextRunAt-second.lastRunAt<259201000);
        assert.deepEqual(second.lastReport.items.map(item=>item.id),['endurance-note-2']);
        report.secondScheduled={plannedAt:new Date(first.nextRunAt).toISOString(),actualAt:new Date(second.lastRunAt).toISOString(),delayMs:second.lastRunAt-first.nextRunAt,reportId:second.lastReport.id};
        await check('72-hour occurrence ran once and ignored already summarized content',report.secondScheduled);
      }
      if(second)assert.equal(state.lastRunAt,second.lastRunAt,'No third scheduled occurrence is due inside 73 hours');
      if(wall>=nextHeartbeat){
        const missed=Math.floor((wall-nextHeartbeat)/3600000);nextHeartbeat+=(missed+1)*3600000;report.heartbeats++;
        await event('hourly-heartbeat',{elapsedMs:wall-startedAt,missedHeartbeatSlots:missed,status:state.status,nextDueAt:state.nextRunAt&&new Date(state.nextRunAt).toISOString(),counts:transport.counts(),memory});await save();
      }
    }
    if(stopReason){report.status='interrupted';report.stopReason=stopReason;process.exitCode=2;}
    else{
      assert.ok(first&&restarted,'Initial timer and durable reopen must complete');
      if(!selfCheck){
        assert.ok(second,'No naturally due 72-hour occurrence was observed before the fixed 73-hour deadline');
        assert.ok(elapsed(startedMono,performance.now(),73*3600000).complete,'Clock change cannot replace 73 hours of elapsed time');
      }
      // Explicit final duplicate request is separate from all natural scheduling observations.
      const before=transport.counts();assert.deepEqual(before,selfCheck?{searches:4,details:1,summaries:1}:{searches:8,details:2,summaries:2},'No extra collection is allowed before the explicit final duplicate request');
      await api('action',{action:'run'});await watcher.whenIdle();
      assert.deepEqual(transport.counts(),{searches:before.searches+4,details:before.details,summaries:before.summaries});
      assert.match(watcher.status().message,/没有新增/);
      assert.equal(createHash('sha256').update(await readFile(first.lastReport.path)).digest('hex'),report.firstReportSha256);
      assert.deepEqual(await sourceHashes(),report.sourceHashes,'Source changed while verification was running');
      assert.equal(rejected.length,0);transport.assertHealthy();
      await check('final manual duplicate consumed no detail or summary and preserved first report');
      report.status=report.clockDiscontinuities.length?'inconclusive-clock-discontinuity':selfCheck?'self-check-passed':report.hostGaps.length?'passed-with-host-gaps':'passed';
      report.threeDayVerificationComplete=!selfCheck&&!report.clockDiscontinuities.length;
      if(report.clockDiscontinuities.length)process.exitCode=2;
    }
  }catch(error){report.status='failed';report.error=error.stack;report.threeDayVerificationComplete=false;process.exitCode=1;}
  finally{
    await watcher?.dispose();await transport?.close();
    report.finishedAt=new Date().toISOString();report.elapsedMs=Date.now()-startedAt;report.monotonicElapsedMs=Math.round(performance.now()-startedMono);
    await event('finished',{status:report.status,elapsedMs:report.elapsedMs,threeDayVerificationComplete:report.threeDayVerificationComplete===true});await save();
    await marker.close();await unlink(join(directory,'runner.lock'));
    process.removeListener('SIGINT',stop);process.removeListener('SIGTERM',stop);
  }
}
