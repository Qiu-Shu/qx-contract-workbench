// Synthetic endurance processes may communicate only with their local HTTP fixture.
import net from 'node:net';
import tls from 'node:tls';
import dgram from 'node:dgram';
import dns from 'node:dns';
import {syncBuiltinESMExports} from 'node:module';

export const rejected=[];
function deny(kind){rejected.push({at:new Date().toISOString(),kind});throw Error('Endurance fixture blocked '+kind);}
function local(host){if(host!=='127.0.0.1')deny('non-loopback transport');}
const connect=net.Socket.prototype.connect;
net.Socket.prototype.connect=function(...args){
  const options=Array.isArray(args[0])?args[0]:args;
  const first=options[0];
  if(first&&typeof first==='object'){if(first.path)deny('IPC transport');local(first.host??'localhost');}
  else if(typeof first==='number')local(typeof options[1]==='string'?options[1]:'localhost');
  else deny('unrecognized transport');
  return Reflect.apply(connect,this,args);
};
tls.connect=()=>deny('TLS');dgram.createSocket=()=>deny('UDP');
const lookup=dns.lookup,promiseLookup=dns.promises.lookup;
dns.lookup=(host,...args)=>{local(host);return lookup(host,...args);};
dns.promises.lookup=(host,...args)=>{local(host);return promiseLookup(host,...args);};
const originalFetch=globalThis.fetch;
globalThis.fetch=(input,options)=>{
  const url=new URL(input instanceof Request?input.url:input);
  if(url.protocol!=='http:')deny('non-HTTP fetch');local(url.hostname);
  return originalFetch(input,{...options,redirect:'error'});
};
syncBuiltinESMExports();
