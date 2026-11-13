// Installed Harness may communicate only with this test's local browser and synthetic providers.
import net from 'node:net';
import {appendFileSync} from 'node:fs';
const allowed=new Set(['127.0.0.1','localhost','::1']);
function deny(target){
  if(process.env.QX_UI_GUARD_LOG)appendFileSync(process.env.QX_UI_GUARD_LOG,JSON.stringify({blocked:String(target)})+'\n');
  throw Error('UI acceptance blocked a non-loopback connection');
}
const originalFetch=globalThis.fetch;
globalThis.fetch=(input,options)=>{
  const url=new URL(input instanceof Request?input.url:input);
  if(url.protocol!=='http:'||!allowed.has(url.hostname))deny(url.origin);
  return originalFetch(input,options);
};
const connect=net.Socket.prototype.connect;
net.Socket.prototype.connect=function(...args){
  const values=Array.isArray(args[0])?args[0]:args,first=values[0];
  const options=first&&typeof first==='object'?first:typeof first==='number'?{port:first,host:typeof values[1]==='string'?values[1]:'localhost'}:{path:first};
  if(!options.path&&!allowed.has(options.host||options.hostname||'localhost'))deny(options.host||options.hostname);
  return connect.apply(this,args);
};
