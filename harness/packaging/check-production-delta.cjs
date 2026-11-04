// Reconstruct the production installer over loopback Range requests; never execute it.
const fs=require('node:fs/promises'),{createReadStream}=require('node:fs');
const path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {once}=require('node:events'),{createRequire}=require('node:module');
const req=createRequire(require.resolve('electron-updater'));
const {HttpExecutor,CancellationToken}=req('builder-util-runtime'),yaml=req('js-yaml');
const {StrictNsisUpdater}=require('../desktop/update-download.cjs');
const {verifyInstaller}=require('../desktop/update-integrity.cjs');
class Executor extends HttpExecutor{createRequest(options,callback){return http.request(options,callback)}download(){throw Error('FULL_DOWNLOAD_FORBIDDEN')}}
async function main(){
  const oldDir=path.resolve(process.argv[2]),nextDir=path.resolve(process.argv[3]);
  const out=await fs.mkdtemp(path.resolve(__dirname,'../.local/production-delta-'));
  const readInfo=async dir=>yaml.load(await fs.readFile(path.join(dir,'latest.yml'),'utf8'));
  const old=await readInfo(oldDir),next=await readInfo(nextDir),key=require('../desktop/update-config.json').publicKey;
  const oldExe=path.join(oldDir,old.files[0].url),nextExe=path.join(nextDir,next.files[0].url);
  await verifyInstaller(oldExe,old,key);await verifyInstaller(nextExe,next,key);
  await fs.link(oldExe,path.join(out,'installer.exe'));
  let transferred=0,ranges=0;
  const server=http.createServer(async(request,response)=>{
    try{
      if(request.url==='/old.blockmap'||request.url==='/new.blockmap'){
        response.end(await fs.readFile((request.url==='/old.blockmap'?oldExe:nextExe)+'.blockmap'));return;
      }
      const match=/^bytes=(\d+)-(\d+)$/.exec(request.headers.range||'');
      if(request.url!=='/next.exe'||!match){response.writeHead(400);response.end();return;}
      const start=Number(match[1]),end=Number(match[2]);assert.ok(start>=0&&end>=start&&end<next.files[0].size);
      ranges++;transferred+=end-start+1;
      response.writeHead(206,{'content-length':end-start+1,'content-range':`bytes ${start}-${end}/${next.files[0].size}`});
      createReadStream(nextExe,{start,end}).on('error',()=>response.destroy()).pipe(response);
    }catch{response.destroy()}
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  const base=`http://127.0.0.1:${server.address().port}`;
  const updater=new StrictNsisUpdater(null,{version:old.version});updater.logger=null;updater.httpExecutor=new Executor();
  updater.downloadedUpdateHelper={cacheDir:out,cacheDirForPendingUpdate:out};
  const provider={getBlockMapFiles:()=>[new URL(base+'/old.blockmap'),new URL(base+'/new.blockmap')]};
  const reconstructed=path.join(out,'reconstructed.exe');let plan;
  updater.on('qx-delta-plan',value=>{plan=value;console.log(JSON.stringify({stage:'plan',...plan}))});
  try{
    await updater.differentialDownloadInstaller({url:new URL(base+'/next.exe'),info:next.files[0]},
      {updateInfoAndProvider:{info:next,provider},requestHeaders:{},cancellationToken:new CancellationToken()},reconstructed,provider,'installer.exe');
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
  await verifyInstaller(reconstructed,next,key);assert.equal(transferred,plan.downloadBytes);assert.ok(transferred<next.files[0].size);
  const report={oldVersion:old.version,newVersion:next.version,...plan,actualDownloadBytes:transferred,rangeRequests:ranges,
    savedPercent:Math.round((1-transferred/next.files[0].size)*10000)/100,productionInstallerReconstructed:true,signatureAndSha512Verified:true,
    scope:'Production installers reconstructed through loopback HTTP; installer not executed',output:out};
  await fs.writeFile(path.join(nextDir,'production-delta-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}
main().catch(error=>{console.error(error);process.exitCode=1});
