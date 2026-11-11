import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,stat,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {EventEmitter} from 'node:events';
import {createXhsRuntime} from './xhs-runtime.mjs';

async function fixture(t){
  const stateDir=await mkdtemp(join(tmpdir(),'qx-content-runtime-'));
  t.after(()=>rm(stateDir,{recursive:true,force:true}));
  await mkdir(join(stateDir,'runtime'));const executable=join(stateDir,'runtime',process.platform==='win32'?'xiaohongshu-mcp.exe':'xiaohongshu-mcp');
  await writeFile(executable,'synthetic file never executed');return {stateDir,executable};
}
function processFixture(){
  const child=new EventEmitter();child.pid=123;child.exitCode=null;child.stderr=new EventEmitter();child.stdout=new EventEmitter();
  child.kills=0;child.kill=()=>{child.kills++;child.exitCode=0;child.emit('exit',0);return true;};return child;
}
function service(token,available=()=>true){
  return async(url,options={})=>{
    if(!available())throw Error('connection refused');
    if(new URL(url).pathname==='/health')return Response.json({success:true,data:{service:'xiaohongshu-mcp'}});
    if(options.headers?.authorization!=='Bearer '+token())return Response.json({code:'UNAUTHORIZED'},{status:401});
    return Response.json({code:'INVALID_REQUEST'},{status:400});
  };
}

test('missing component reports a recoverable preparation state and never spawns',async t=>{
  const {stateDir,executable}=await fixture(t);await rm(executable);
  const runtime=createXhsRuntime({stateDir,fetchImpl:async()=>{throw Error('offline');},spawnImpl:()=>assert.fail('no spawn')});
  await assert.rejects(runtime.ensureStarted(),error=>error.code==='COMPONENT_MISSING'&&error.message.includes('准备'));
  await runtime.stop();
});

test('one owned process starts with loopback binding, protected credentials and deduplicated readiness',async t=>{
  const {stateDir}=await fixture(t);const child=processFixture();let calls=0,running=false,spawnOptions;
  let runtime;
  runtime=createXhsRuntime({stateDir,fetchImpl:service(()=>runtime.authToken,()=>running),spawnImpl:(file,args,options)=>{calls++;running=true;spawnOptions={file,args,options};return child;}});
  const [first,second]=await Promise.all([runtime.ensureStarted(),runtime.ensureStarted()]);
  assert.deepEqual(first,{ready:true});assert.deepEqual(second,{ready:true});assert.equal(calls,1);
  assert.ok(spawnOptions.args.includes('-port=127.0.0.1:18060'));
  assert.equal(spawnOptions.options.shell,false);assert.equal(spawnOptions.options.env.AUTH_TOKEN,runtime.authToken);
  assert.equal(spawnOptions.options.env.COOKIES_PATH,join(stateDir,'auth','cookies.json'));
  assert.match(runtime.authToken,/^[a-f0-9]{64}$/);
  assert.equal(JSON.stringify(first).includes(runtime.authToken),false);
  assert.equal(await readFile(join(stateDir,'auth','cookies.json'),'utf8'),'[]');
  if(process.platform!=='win32'){
    assert.equal((await stat(join(stateDir,'auth','cookies.json'))).mode&0o777,0o600);
    assert.equal((await stat(join(stateDir,'auth','service-token'))).mode&0o777,0o600);
  }
  await runtime.stop();assert.equal(child.kills,1);
});

test('an already running authenticated instance is reused without taking ownership',async t=>{
  const {stateDir}=await fixture(t);const token='a'.repeat(64);
  await mkdir(join(stateDir,'auth'));await writeFile(join(stateDir,'auth','service-token'),token);
  const runtime=createXhsRuntime({stateDir,fetchImpl:service(()=>token),spawnImpl:()=>assert.fail('must not spawn')});
  assert.deepEqual(await runtime.ensureStarted(),{ready:true});assert.equal(runtime.authToken,token);
  await runtime.stop();
});

test('a different or unauthenticated server is never adopted or killed',async t=>{
  const {stateDir}=await fixture(t);
  const runtime=createXhsRuntime({stateDir,fetchImpl:async(url)=>new URL(url).pathname==='/health'?Response.json({success:true,data:{service:'xiaohongshu-mcp'}}):Response.json({code:'INVALID_REQUEST'},{status:400}),spawnImpl:()=>assert.fail('must not spawn')});
  await assert.rejects(runtime.ensureStarted(),error=>error.code==='COMPONENT_UNAVAILABLE');
  await runtime.stop();
});

test('failed startup cleans up the owned process and allows a later attempt',async t=>{
  const {stateDir}=await fixture(t);let child;let spawns=0;
  const runtime=createXhsRuntime({stateDir,readyTimeoutMs:15,pollMs:1,fetchImpl:async()=>{throw Error('secret URL token must not escape');},spawnImpl:()=>{spawns++;child=processFixture();return child;}});
  await assert.rejects(runtime.ensureStarted(),error=>error.code==='COMPONENT_UNAVAILABLE'&&!error.message.includes('secret'));
  assert.equal(child.kills,1);
  await assert.rejects(runtime.ensureStarted(),error=>error.code==='COMPONENT_UNAVAILABLE');assert.equal(spawns,2);
  await runtime.stop();
});

test('stop during readiness rejects cleanly and does not leave a process behind',async t=>{
  const {stateDir}=await fixture(t);const child=processFixture();let spawned;
  const didSpawn=new Promise(resolve=>{spawned=resolve;});
  const runtime=createXhsRuntime({stateDir,pollMs:1,fetchImpl:async()=>{throw Error('not ready');},spawnImpl:()=>{spawned();return child;}});
  const starting=runtime.ensureStarted();await didSpawn;await runtime.stop();
  await assert.rejects(starting,error=>error.code==='COMPONENT_UNAVAILABLE');assert.equal(child.kills,1);
});
