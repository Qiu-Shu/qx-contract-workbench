const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const http=require('node:http');
const {once}=require('node:events');
const {createHash}=require('node:crypto');
const {gzipSync}=require('node:zlib');
const {createRequire}=require('node:module');
const {HttpExecutor,CancellationToken,configureRequestOptionsFromUrl}=createRequire(require.resolve('electron-updater'))('builder-util-runtime');
const {StrictNsisUpdater}=require('./update-download.cjs');
class Executor extends HttpExecutor{
  createRequest(options,callback){return http.request(options,callback)}
  download(url,destination,options){return options.cancellationToken.createPromise((resolve,reject,onCancel)=>this.doDownload(configureRequestOptionsFromUrl(url,{headers:options.headers}),{destination,options,onCancel,callback:error=>error?reject(error):resolve(destination),responseHandler:null},0));}
}
const blockSize=256*1024;
function map(bytes){const sizes=[],checksums=[];for(let offset=0;offset<bytes.length;offset+=blockSize){const block=bytes.subarray(offset,offset+blockSize);sizes.push(block.length);checksums.push(createHash('sha256').update(block).digest('base64'));}return {version:'2',files:[{name:'file',offset:0,sizes,checksums}]};}
async function fixture(t,mode='range'){
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'qx-real-delta-'));
  const old=Buffer.concat(Array.from({length:8},(_,i)=>Buffer.alloc(blockSize,i+1)));
  const next=Buffer.from(old);next.fill(23,blockSize*3,blockSize*4);
  await fs.writeFile(path.join(directory,'installer.exe'),old);
  if(mode==='cache-mismatch'){const stale=Buffer.from(old);stale[0]^=1;await fs.writeFile(path.join(directory,'installer.exe'),stale);}
  const requests=[];let transferred=0,closed=false,disconnected=false;
  let markStalled;const stalled=new Promise(resolve=>{markStalled=resolve});
  const server=http.createServer((req,res)=>{
    requests.push({path:req.url,range:req.headers.range});
    if(req.url.startsWith('/latest.yml')){res.end(JSON.stringify({version:'0.2.4',files:[{url:'Qunxing-Workbench-0.2.4-Setup.exe',size:next.length,sha512:createHash('sha512').update(next).digest('base64')}]}));return;}
    if(req.url.endsWith('.blockmap')){res.end(gzipSync(JSON.stringify(map(req.url==='/old.blockmap'||req.url.includes('0.2.3')?old:next))));return;}
    if(mode==='disconnect-once'&&!disconnected){disconnected=true;req.socket.destroy();return;}
    if(mode==='no-range'){res.writeHead(200,{'content-length':next.length});res.end(next);return;}
    if(mode==='stall'){res.writeHead(206,{'content-length':blockSize,'content-range':`bytes ${3*blockSize}-${4*blockSize-1}/${next.length}`});res.flushHeaders();res.on('close',()=>{closed=true});markStalled();return;}
    const match=/^bytes=(\d+)-(\d+)$/.exec(req.headers.range||'');
    if(!match){const body=Buffer.from(next);if(mode==='corrupt')body[0]^=1;res.writeHead(200,{'content-length':body.length});res.end(body);return;}
    const start=Number(match[1]),end=Number(match[2]);
    const body=Buffer.from(next.subarray(start,end+1));if(mode==='corrupt')body[0]^=1;
    transferred+=body.length;res.writeHead(206,{'content-length':body.length,'content-range':`bytes ${start}-${end}/${next.length}`});res.end(body);
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  t.after(async()=>{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));await fs.rm(directory,{recursive:true,force:true});});
  const base=`http://127.0.0.1:${server.address().port}`;
  const updater=new StrictNsisUpdater(null,{version:'0.2.3'});updater.logger=null;updater.httpExecutor=new Executor();
  updater.downloadedUpdateHelper={cacheDir:directory,cacheDirForPendingUpdate:directory};
  const provider={getBlockMapFiles:()=>[new URL(base+'/old.blockmap'),new URL(base+'/new.blockmap')]};
  const info={size:next.length,sha512:createHash('sha512').update(next).digest('base64')};
  const output=path.join(directory,'new.exe');
  const token=new CancellationToken();
  const run=()=>updater.differentialDownloadInstaller({url:new URL(base+'/installer.exe'),info},{updateInfoAndProvider:{info:{version:'0.2.4'},provider},requestHeaders:{},cancellationToken:token},output,provider,'installer.exe');
  return {updater,old,next,output,directory,requests,run,token,stalled,base,closed:()=>closed,transferred:()=>transferred};
}
for(const mode of ['range','no-range','cache-mismatch','disconnect-once','corrupt'])test('full upstream check/download flow recovers when delta cannot complete: '+mode,async t=>{
  const f=await fixture(t,mode);
  const config=path.join(f.directory,'app-update.yml');await fs.writeFile(config,JSON.stringify({updaterCacheDirName:'qx-test-updater'}));
  Object.assign(f.updater.app,{isPackaged:true,userDataPath:f.directory,baseCachePath:f.directory,appUpdateConfigPath:config,whenReady:async()=>{}});
  const {DownloadedUpdateHelper}=require('electron-updater/out/DownloadedUpdateHelper');
  f.updater.downloadedUpdateHelper=new DownloadedUpdateHelper(f.directory);
  f.updater.setFeedURL({provider:'generic',url:f.base,useMultipleRangeRequest:false});
  f.updater.autoDownload=false;f.updater.autoInstallOnAppQuit=false;f.updater.disableWebInstaller=true;f.updater.disableDifferentialDownload=false;
  await f.updater.checkForUpdates();
  if(mode==='corrupt'){await assert.rejects(f.updater.downloadUpdate(),/checksum/i);assert.equal(f.updater.installerPath,null);return;}
  const [file]=await f.updater.downloadUpdate();assert.deepEqual(await fs.readFile(file),f.next);
  const full=f.requests.filter(r=>r.path.endsWith('.exe')&&!r.range);
  assert.equal(full.length,['range','disconnect-once'].includes(mode)?0:1);
  if(mode==='range')assert.equal(f.transferred(),blockSize);
});
test('cancellation closes a stalled HTTP Range and settles promptly',async t=>{
  const f=await fixture(t,'stall');let settled=false;
  const download=f.run().catch(error=>{settled=true;return error});
  await f.stalled;f.token.cancel();await new Promise(resolve=>setTimeout(resolve,250));
  assert.equal(settled,true);assert.equal(f.closed(),true);assert.match((await download).message,/cancel/i);
});
test('real HTTP delta transfers only changed bytes and reconstructs the exact installer',async t=>{
  const f=await fixture(t);assert.equal(await f.run(),false);
  assert.deepEqual(await fs.readFile(f.output),f.next);
  assert.equal(f.transferred(),blockSize);assert.equal(f.next.length,blockSize*8);
  assert.ok(f.requests.filter(r=>r.path==='/installer.exe').every(r=>r.range));
});
test('server ignoring Range selects a separate full download',async t=>{
  const f=await fixture(t,'no-range');assert.equal(await f.run(),true);
});
test('corrupt downloaded block cannot be accepted as a completed delta',async t=>{
  const f=await fixture(t,'corrupt');assert.equal(await f.run(),true);
});
test('missing cached installer selects full download without requesting blockmaps',async t=>{
  const f=await fixture(t);await fs.unlink(path.join(f.directory,'installer.exe'));
  assert.equal(await f.run(),true);assert.equal(f.requests.length,0);
});

test('retry is bounded and cancellation or disk errors never start a full download',async t=>{
  const f=await fixture(t);let attempts=0;const modes=[];
  f.updater.on('qx-download-mode',event=>modes.push(event.mode));
  f.updater.downloadDelta=async()=>{attempts++;throw Object.assign(Error('connection reset'),{code:'ECONNRESET'});};
  assert.equal(await f.run(),true);assert.equal(attempts,2);assert.deepEqual(modes,['retry','full']);
  for(const code of ['ENOSPC','EACCES','EPERM','EROFS']){
    modes.length=0;f.updater.downloadDelta=async()=>{throw Object.assign(Error(code),{code});};
    await assert.rejects(f.run(),{code});assert.deepEqual(modes,[]);
  }
  modes.length=0;f.token.cancel();await assert.rejects(f.run());assert.deepEqual(modes,[]);
});
test('failed installer process launch keeps the application running',async t=>{
  const f=await fixture(t);let quits=0;f.updater.app.quit=()=>{quits++};
  f.updater.downloadedUpdateHelper.file=path.join(f.directory,'does-not-exist.exe');
  await assert.rejects(f.updater.quitAndInstall(),/ENOENT/);assert.equal(quits,0);
});
