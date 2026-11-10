// Detached supervisor: receives a key only in process memory, never reads a UI profile.
const {claimLauncher}=require('./installed-stop.cjs');
const {runHost}=require('./installed-runtime.cjs');
const {createEventLog}=require('./host-recovery.cjs');
const data=process.env.QX_INSTALL_DATA,payload=process.env.QX_PAYLOAD_ROOT;
const secret=process.env.DEEPSEEK_API_KEY;
if(!data||!payload||!secret)process.exit(1);
delete process.env.DEEPSEEK_API_KEY;
const log=createEventLog(data,'host');
log('launcher_start');
process.on('exit',code=>log('launcher_exit',{code}));
process.on('uncaughtExceptionMonitor',error=>log('launcher_exception',{errorName:error.name,errorCode:error.code}));
let supervisor;
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{
  log('launcher_signal',{signal});if(supervisor)supervisor.stop();else process.exit(0);
});
claimLauncher(data).then(()=>runHost({payload,data,app:{exit:code=>process.exit(code)},
  store:{withSecret:async consumer=>{await consumer(secret);return {status:'saved'}}},
})).then(value=>{supervisor=value}).catch(error=>{log(error.code==='EADDRINUSE'?'launcher_lock_failed':'launcher_start_failed',{errorName:error.name,errorCode:error.code});process.exit(1)});
