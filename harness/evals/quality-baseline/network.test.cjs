const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),http=require('node:http');
const {spawn}=require('node:child_process');
const policy=path.join(__dirname,'network-policy.cjs');
function child(code,env={},command=process.execPath,flags=['-e']){
 return new Promise((resolve,reject)=>{
  const p=spawn(command,[...flags,code],{env:{...process.env,...env},windowsHide:true});let stdout='',stderr='';
  p.stdout.on('data',b=>stdout+=b);p.stderr.on('data',b=>stderr+=b);p.on('error',reject);
  const timer=setTimeout(()=>{p.kill();reject(Error('Network probe timeout'));},10000);
  p.on('close',status=>{clearTimeout(timer);resolve({status,stdout,stderr});});
 });
}
test('default evaluation policy prevents HTTP reaching a real local receiver',async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-network-'));let received=0;
 const server=http.createServer((_req,res)=>{received++;res.end('synthetic');});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port;
 const request=`require('node:http').get(${JSON.stringify(url)},r=>{r.resume();r.on('end',()=>console.log('reached'));}).on('error',e=>console.log(e.code));`;
 try{
  assert.equal((await child(request)).stdout.trim(),'reached');assert.equal(received,1);
  const code=`if(require('node:fs').existsSync(${JSON.stringify(policy)}))require(${JSON.stringify(policy)}).install({log:${JSON.stringify(path.join(tmp,'network.jsonl'))},python:process.env.QX_TEST_PYTHON});try{${request}}catch(e){console.log(e.code)}`;
  const result=await child(code);
  assert.equal(result.status,0,result.stderr);assert.equal(result.stdout.trim(),'EVAL_NETWORK_DENIED');assert.equal(received,1);
 }finally{await new Promise(r=>server.close(r));fs.rmSync(tmp,{recursive:true,force:true});}
});

test('fetch, TLS, raw TCP, UDP, DNS, ESM imports, workers and arbitrary children are denied and recorded',async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-network-')),log=path.join(tmp,'network.jsonl');
 const code=`
 const fs=require('node:fs');
 // DNS originals are fake receivers so a broken policy can never query the real resolver in this test.
 const dns=require('node:dns');dns.lookup=()=>{throw Error('DNS escaped')};dns.promises.resolve4=async()=>{throw Error('DNS escaped')};
 const p=require(${JSON.stringify(policy)});p.install({log:${JSON.stringify(log)},python:process.env.QX_TEST_PYTHON});
 const attempts=[()=>fetch('http://127.0.0.1:9'),()=>require('node:https').get('https://127.0.0.1:9'),
 ()=>require('node:net').connect(9,'127.0.0.1'),()=>dns.lookup('localhost'),()=>dns.promises.resolve4('localhost'),
 ()=>new dns.Resolver().resolve4('localhost'),
 ()=>{const s=require('node:dgram').createSocket('udp4');try{s.send('synthetic',9,'127.0.0.1')}finally{s.close()}},
 ()=>require('node:child_process').spawn(process.execPath,['-e','process.exit(0)'],{env:{}}),
 ()=>require('node:child_process').execSync('unused'),()=>new(require('node:worker_threads').Worker)('process.exit(0)',{eval:true}),
 async()=>{const {connect}=await import('node:net');connect(9,'127.0.0.1')},
 ()=>p.modelFetch('https://api.deepseek.com/chat/completions',{method:'POST'})];
 (async()=>{for(const attempt of attempts){try{await attempt();throw Error('Request escaped')}catch(e){if(e.code!=='EVAL_NETWORK_DENIED')throw e;}}console.log(attempts.length)})().catch(e=>{console.error(e);process.exitCode=1});`;
 try{
  const result=await child(code,{QX_EVAL_MODE:'scripted'});assert.equal(result.status,0,result.stderr);assert.equal(result.stdout.trim(),'12');
  const summary=require('./network-policy.cjs').summarize(log);assert.equal(summary.deniedAttempts,12);assert.equal(summary.passed,false);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});

test('Python guard denies network and grandchildren while preserving asyncio socketpair',async()=>{
 const python=process.env.QX_TEST_PYTHON||(process.platform==='win32'?'python':'python3');
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-network-python-')),log=path.join(tmp,'network.jsonl');
 const code=`import importlib.util, pathlib, socket, subprocess, sys\n`+
 `spec=importlib.util.spec_from_file_location('guard',${JSON.stringify(path.join(__dirname,'guarded-python.py'))})\n`+
 `guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard);guard.install(${JSON.stringify(log)})\n`+
 `import asyncio\nasync def local():\n    await asyncio.sleep(0)\nasyncio.run(local())\n`+
 `checks=[lambda:socket.create_connection(('127.0.0.1',9)),lambda:socket.getaddrinfo('localhost',9),`+
 `lambda:socket.socket(socket.AF_INET,socket.SOCK_DGRAM).sendto(b'synthetic',('127.0.0.1',9)),`+
 `lambda:subprocess.run([sys.executable,'-c','print(1)'],env={})]\n`+
 `for check in checks:\n    try:\n        check()\n        raise AssertionError('Request escaped')\n    except PermissionError as error:\n        assert 'EVAL_NETWORK_DENIED' in str(error)\nprint(len(checks))\n`;
 try{
  const result=await child(code,{},python,['-c']);assert.equal(result.status,0,result.stderr);assert.equal(result.stdout.trim(),'4');
  assert.equal(require('./network-policy.cjs').summarize(log).deniedAttempts,4);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});

test('pinned Promptfoo disabled telemetry produces no network attempt after the in-memory patch',async t=>{
 const telemetry=path.join(__dirname,'node_modules/promptfoo/dist/src/telemetry-CIqy4fSC.js');
 if(!fs.existsSync(telemetry)){t.skip('Isolated Promptfoo development dependencies are not installed');return;}
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-telemetry-')),log=path.join(tmp,'network.jsonl');
 const code=`import(${JSON.stringify(require('node:url').pathToFileURL(telemetry).href)}).then(m=>{const p=new m.t(false);p.record('eval_ran',{});p.record('eval_ran',{});console.log('done')}).catch(e=>{console.error(e);process.exitCode=1});`;
 try{
  const result=await child(code,{QX_EVAL_NETWORK_LOG:log,QX_EVAL_MODE:'scripted',PROMPTFOO_DISABLE_TELEMETRY:'1',PROMPTFOO_CONFIG_DIR:tmp},process.execPath,['--require',path.join(__dirname,'preload.cjs'),'-e']);
  assert.equal(result.status,0,result.stderr);assert.equal(result.stdout.trim(),'done');
  const summary=require('./network-policy.cjs').summarize(log);assert.equal(summary.telemetryPatched,true);assert.equal(summary.deniedAttempts,0);assert.equal(summary.modelRequests,0);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
