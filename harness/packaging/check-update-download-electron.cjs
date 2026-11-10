// Run with Electron, passing the staged app directory and an isolated output directory.
// Uses fictional bytes over loopback; never starts an installer or opens a window.
const {app}=require('electron');
const fs=require('node:fs/promises'),path=require('node:path'),http=require('node:http');
const {once}=require('node:events'),{createRequire}=require('node:module');
const {createHash,generateKeyPairSync,sign}=require('node:crypto'),{gzipSync}=require('node:zlib');
const assert=require('node:assert/strict');
const root=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
const req=createRequire(path.join(root,'package.json'));
app.setPath('userData',path.join(out,'electron-user'));
process.on('uncaughtException',()=>app.exit(1));process.on('unhandledRejection',()=>app.exit(1));
async function main(){
  await fs.mkdir(out,{recursive:true});
  const {StrictNsisUpdater}=req('./update-download.cjs');
  const {createUpdateController}=req('./updates.cjs'),{releasePayload}=req('./update-integrity.cjs');
  const {DownloadedUpdateHelper}=req('electron-updater/out/DownloadedUpdateHelper');
  const {ElectronHttpExecutor,getNetSession}=req('electron-updater/out/electronHttpExecutor');
  await getNetSession().setProxy({mode:'direct'});
  const old=Buffer.concat([Buffer.alloc(256*1024,1),Buffer.alloc(256*1024,2)]);
  const next=Buffer.from(old);next.fill(3,256*1024);
  const map=bytes=>({version:'2',files:[{name:'file',offset:0,sizes:[256*1024,256*1024],checksums:[bytes.subarray(0,256*1024),bytes.subarray(256*1024)].map(b=>createHash('sha256').update(b).digest('base64'))}]});
  const {publicKey,privateKey}=generateKeyPairSync('ed25519');
  const info={version:'0.2.16',files:[{url:'Qunxing-Workbench-0.2.16-Setup.exe',size:next.length,sha512:createHash('sha512').update(next).digest('base64')}],releaseNotes:'Synthetic update test'};
  info.qxSignature=sign(null,releasePayload(info),privateKey).toString('base64');
  let full=0,ranges=0,redirects=0,stall=false,closed=false,startStall;
  const stalled=new Promise(resolve=>{startStall=resolve});
  const server=http.createServer((request,response)=>{
    if(request.url.startsWith('/latest.yml')){response.end(JSON.stringify(info));return;}
    if(request.url.endsWith('.blockmap')){response.end(gzipSync(JSON.stringify(map(request.url.includes('0.2.14')?old:next))));return;}
    const range=/^bytes=(\d+)-(\d+)$/.exec(request.headers.range||'');
    if(range){ranges++;const start=Number(range[1]),end=Number(range[2]);response.writeHead(206,{'content-range':`bytes ${start}-${end}/${next.length}`,'content-length':end-start+1});response.end(next.subarray(start,end+1));}
    else if(request.url!=='/payload.exe'){redirects++;response.writeHead(302,{location:'/payload.exe'});response.end();}
    else{full++;response.writeHead(200,{'content-length':next.length});if(stall){response.on('close',()=>{closed=true});response.flushHeaders();startStall();}else response.end(next);}
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  try{
    const cache=path.join(out,'updater-cache');await fs.mkdir(cache);
    const stale=Buffer.from(old);stale[0]^=1;await fs.writeFile(path.join(cache,'installer.exe'),stale);
    const config=path.join(out,'app-update.yml');await fs.writeFile(config,JSON.stringify({updaterCacheDirName:'qx-test-updater'}));
    const updater=new StrictNsisUpdater(null,{version:'0.2.14',isPackaged:true,userDataPath:out,baseCachePath:out,appUpdateConfigPath:config,whenReady:async()=>{}});
    updater.httpExecutor=new ElectronHttpExecutor();updater.downloadedUpdateHelper=new DownloadedUpdateHelper(cache);
    updater.setFeedURL({provider:'generic',url:`http://127.0.0.1:${server.address().port}`,useMultipleRangeRequest:false});
    const states=[];const controller=createUpdateController({updater,version:'0.2.14',publicKey:publicKey.export({type:'spki',format:'pem'}),prepareInstall:async()=>assert.fail('No install allowed'),confirmInstall:async()=>false,onState:state=>states.push(state)});
    await controller.check();await controller.download();
    assert.equal(controller.state().phase,'downloaded');assert.equal(full,1);assert.equal(ranges,1);
    assert.ok(states.some(s=>s.downloadMode==='full'&&s.progress===0));
    assert.deepEqual(await fs.readFile(updater.installerPath),next);
    stall=true;updater.downloadedUpdateHelper=new DownloadedUpdateHelper(path.join(out,'cancel-cache'));
    const token=new (req('builder-util-runtime').CancellationToken)();
    const pending=updater.downloadUpdate(token);const rejected=assert.rejects(pending,/cancel/i);
    await stalled;token.cancel();await rejected;await new Promise(resolve=>setTimeout(resolve,100));
    assert.equal(closed,true);assert.equal(updater.installerPath,null);
    await fs.writeFile(path.join(out,'report.json'),JSON.stringify({passed:true,realElectronHttp:true,staleCacheRecovered:true,rangeRequests:ranges,fullDownloads:full,redirects,fullCancelConnectionClosed:true,signedReleaseAndDownloadedBytesVerified:true,installerExecuted:false},null,2));
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
}
const timeout=setTimeout(()=>app.exit(2),60000);
app.whenReady().then(main).then(()=>{clearTimeout(timeout);app.exit(0)},async error=>{await fs.mkdir(out,{recursive:true});await fs.writeFile(path.join(out,'failure.txt'),String(error.stack));app.exit(1)});
