const fs=require('node:fs');
const path=require('node:path');

function createEventLog(data,scope,{maxBytes=1024*1024}={}){
  const directory=path.join(data,'.local'),file=path.join(directory,`${scope}-events.jsonl`);
  return (event,fields={})=>{
    // Never serialize an Error, request, environment, URL or conversation content.
    const record={time:new Date().toISOString(),pid:process.pid,event};
    for(const key of ['childPid','launcherPid','code','attempt','delayMs','exitCode'])
      if(Number.isSafeInteger(fields[key])||fields[key]===null)record[key]=fields[key];
    for(const key of ['signal','reason','phase','errorCode','errorName'])
      if(typeof fields[key]==='string'&&/^[a-zA-Z0-9_-]{1,64}$/.test(fields[key]))record[key]=fields[key];
    if(typeof fields.intentional==='boolean')record.intentional=fields.intentional;
    try{
      fs.mkdirSync(directory,{recursive:true});
      if(fs.existsSync(file)&&fs.statSync(file).size>=maxBytes){
        fs.rmSync(file+'.1',{force:true});fs.renameSync(file,file+'.1');
      }
      fs.appendFileSync(file,JSON.stringify(record)+'\n');
    }catch{/* A log write failure must not take down the workbench. */}
  };
}

function createSupervisor({start,kill=child=>child.kill(),onState=()=>{},onStopped=()=>{},log=()=>{},
  delays=[1000,3000,10000],stableMs=300000,startupMs=120000}){
  let child=null,timer=null,startup=null,attempt=0,stopping=false,readyAt=0,phase='idle';
  const state=next=>{phase=next;onState({phase,attempt,hostPid:child?.pid||null});};
  function stopped(){state('stopped');onStopped();}
  function failed(code,signal){
    clearTimeout(startup);startup=null;
    log('child_exit',{childPid:child?.pid||null,code,signal,intentional:stopping});child=null;
    if(stopping){stopped();return;}
    if(readyAt&&Date.now()-readyAt>=stableMs)attempt=0;
    readyAt=0;
    if(attempt>=delays.length){state('failed');log('recovery_exhausted',{attempt});return;}
    const delayMs=delays[attempt++];state('recovering');log('recovery_scheduled',{attempt,delayMs});
    timer=setTimeout(()=>{timer=null;launch();},delayMs);
  }
  function launch(){
    if(stopping||child||timer)return;
    state('starting');
    try{
      child=start(()=>{
        if(stopping)return;
        clearTimeout(startup);startup=null;readyAt=Date.now();state('running');log('child_ready',{childPid:child?.pid});
      });
      log('child_start',{childPid:child.pid,attempt});
      state('starting');
      child.once('error',error=>log('child_error',{errorCode:error.code,errorName:error.name}));
      child.once('close',failed);
      startup=setTimeout(()=>{log('startup_timeout',{childPid:child?.pid});if(child)kill(child);},startupMs);
      startup.unref?.();
    }catch(error){log('child_start_error',{errorCode:error.code,errorName:error.name});failed(null,null);}
  }
  return {
    start:launch,
    retry(){if(child||timer||stopping)return false;attempt=0;launch();return true;},
    stop(){
      if(stopping)return;stopping=true;clearTimeout(timer);timer=null;clearTimeout(startup);startup=null;
      log('stop_requested',{intentional:true});
      if(child){state('stopping');kill(child);}else stopped();
    },
    state:()=>({phase,attempt}),
  };
}

function createHostMonitor({probe,recover,isPaused=()=>false,onState=()=>{},log=()=>{},maxAttempts=3,stableMs=300000}){
  let state={phase:'connected',attempt:0},busy=false,attempt=0,healthySince=0,connectedIdentity=null,observedIdentity=null;
  const identity=runtime=>runtime?JSON.stringify([runtime.url,runtime.hostPid,runtime.launcherPid]):null;
  const set=phase=>{
    if(state.phase===phase&&state.attempt===attempt)return;
    state={phase,attempt};log('connection_state',state);onState({...state});
  };
  return {
    state:()=>({...state}),
    connected(runtime){connectedIdentity=identity(runtime)||observedIdentity;healthySince=Date.now();set('connected');},
    reset(){attempt=0;healthySince=0;set('recovering');},
    async tick(){
      if(busy||isPaused())return;busy=true;
      try{
        const host=await probe();if(isPaused())return;
        if(host.runtime){
          observedIdentity=identity(host.runtime);
          if(!connectedIdentity&&state.phase==='connected')connectedIdentity=observedIdentity;
          if(!healthySince)healthySince=Date.now();
          if(Date.now()-healthySince>=stableMs)attempt=0;
          if(state.phase!=='connected'||connectedIdentity!==observedIdentity)set('ready');
          return;
        }
        healthySince=0;
        if(['stopping','stopped'].includes(host.state?.phase)){set('stopped');return;}
        if(host.control||host.hostAlive){
          set(host.state?.phase==='failed'?'failed':['starting','recovering'].includes(host.state?.phase)?'recovering':'disconnected');return;
        }
        if(attempt>=maxAttempts){set('failed');return;}
        attempt++;set('recovering');log('launcher_recovery',{attempt});
        await recover();
      }catch(error){log('launcher_recovery_error',{attempt,errorName:error.name,errorCode:error.code});set(attempt>=maxAttempts?'failed':'disconnected');}
      finally{busy=false;}
    },
  };
}
module.exports={createSupervisor,createHostMonitor,createEventLog};
