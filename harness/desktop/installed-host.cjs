// Detached supervisor: receives a key only in process memory, never reads a UI profile.
const net=require('node:net');
const {createHash}=require('node:crypto');
const {runHost}=require('./installed-runtime.cjs');
const data=process.env.QX_INSTALL_DATA,payload=process.env.QX_PAYLOAD_ROOT;
const secret=process.env.DEEPSEEK_API_KEY;
if(!data||!payload||!secret)process.exit(1);
delete process.env.DEEPSEEK_API_KEY;
const mutex=net.createServer(socket=>socket.end());
const pipe='\\\\.\\pipe\\qx-host-'+createHash('sha256').update(data.toLowerCase()).digest('hex').slice(0,24);
mutex.once('error',()=>process.exit(1));
mutex.listen(pipe,()=>runHost({payload,data,app:{exit:code=>process.exit(code)},
  store:{withSecret:async consumer=>{await consumer(secret);return {status:'saved'}}},
}).catch(()=>process.exit(1)));
