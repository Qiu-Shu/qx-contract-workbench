// Detached supervisor: receives a key only in process memory, never reads a UI profile.
const net=require('node:net');
const {createHash}=require('node:crypto');
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
const mutex=net.createServer(socket=>socket.end());
const pipe='\\\\.\\pipe\\qx-host-'+createHash('sha256').update(data.toLowerCase()).digest('hex').slice(0,24);
mutex.once('error',error=>{log('launcher_lock_failed',{errorCode:error.code});process.exit(1)});
mutex.listen(pipe,()=>runHost({payload,data,app:{exit:code=>process.exit(code)},
  store:{withSecret:async consumer=>{await consumer(secret);return {status:'saved'}}},
}).then(value=>{supervisor=value}).catch(error=>{log('launcher_start_failed',{errorName:error.name,errorCode:error.code});process.exit(1)}));
