// Real NSIS installers with an isolated test identity; never publish these fixtures.
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const http=require('node:http');
const {once}=require('node:events');
const {spawn}=require('node:child_process');
const {createRequire}=require('node:module');
const {build}=require('D:/qx-contract-workbench-20261102/desktop/node_modules/electron-builder');
const {HttpExecutor,CancellationToken}=createRequire(require.resolve('electron-updater'))('builder-util-runtime');
const yaml=createRequire(require.resolve('electron-updater'))('js-yaml');
const {StrictNsisUpdater}=require('../desktop/update-download.cjs');
const root=path.resolve(__dirname,'..','.local/update-checks/nsis');
class Executor extends HttpExecutor{createRequest(o,cb){return http.request(o,cb)}download(){throw Error('FULL_DOWNLOAD_FORBIDDEN')}}
const run=(file,args)=>new Promise((resolve,reject)=>{const child=spawn(file,args,{windowsHide:true,stdio:'ignore'});child.once('error',reject);child.once('exit',code=>code===0?resolve():reject(Error('Process exit '+code)));});
async function main(){
  await fs.mkdir(root,{recursive:true});
  const payload=path.join(root,'payload'),app=path.join(root,'app');
  await fs.mkdir(payload,{recursive:true});await fs.mkdir(app,{recursive:true});
  await fs.mkdir(path.join(payload,'resources'),{recursive:true});
  await fs.copyFile('C:/Windows/System32/where.exe',path.join(payload,'QunxingDeltaTest.exe'));
  const bytes=crypto.randomBytes(8*1024*1024);await fs.writeFile(path.join(payload,'unchanged.bin'),bytes);
  const releases=[];
  for(const version of ['0.2.3','0.2.4']){
    await fs.writeFile(path.join(payload,'中文资料.txt'),'独立安装验收 '+version);
    await fs.writeFile(path.join(app,'package.json'),JSON.stringify({name:'qunxing-delta-qa',version,main:'index.cjs',description:'Isolated updater test',author:'QA'}));
    const directory=path.join(root,version);
    await build({publish:'never',projectDir:app,prepackaged:payload,config:{appId:'cn.qunxing.delta-qa.20261103',productName:'QunxingDeltaTest',electronVersion:'44.8.0',npmRebuild:false,
      directories:{output:directory},publish:{provider:'generic',url:'https://example.invalid/updates/'},
      win:{executableName:'QunxingDeltaTest',target:[{target:'nsis',arch:['x64']}],signAndEditExecutable:false,artifactName:'Qunxing-Workbench-${version}-Setup.${ext}'},
      nsis:{oneClick:true,perMachine:false,runAfterFinish:false,createDesktopShortcut:false,createStartMenuShortcut:false,differentialPackage:true,useZip:false}}});
    releases.push({directory,version,exe:path.join(directory,`Qunxing-Workbench-${version}-Setup.exe`)});
  }
  const [old,next]=releases;
  const cache=path.join(root,'cache');await fs.mkdir(cache,{recursive:true});await fs.copyFile(old.exe,path.join(cache,'installer.exe'));
  let transferred=0,ranges=0;
  const newBytes=await fs.readFile(next.exe);
  const server=http.createServer(async(req,res)=>{
    if(req.url.endsWith('.blockmap')){res.end(await fs.readFile((req.url.startsWith('/old')?old:next).exe+'.blockmap'));return;}
    const match=/^bytes=(\d+)-(\d+)$/.exec(req.headers.range||'');
    if(!match){res.writeHead(400);res.end();return;}
    const start=Number(match[1]),end=Number(match[2]);const part=newBytes.subarray(start,end+1);
    transferred+=part.length;ranges++;res.writeHead(206,{'content-length':part.length,'content-range':`bytes ${start}-${end}/${newBytes.length}`});res.end(part);
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  const base=`http://127.0.0.1:${server.address().port}`;
  const updater=new StrictNsisUpdater(null,{version:old.version});updater.logger=null;updater.httpExecutor=new Executor();updater.downloadedUpdateHelper={cacheDir:cache,cacheDirForPendingUpdate:cache};
  const info=yaml.load(await fs.readFile(path.join(next.directory,'latest.yml'),'utf8')).files[0];
  const provider={getBlockMapFiles:()=>[new URL(base+'/old.blockmap'),new URL(base+'/new.blockmap')]};
  const reconstructed=path.join(root,'reconstructed.exe');
  try{
    await updater.differentialDownloadInstaller({url:new URL(base+'/next.exe'),info},{updateInfoAndProvider:{info:{version:next.version},provider},requestHeaders:{},cancellationToken:new CancellationToken()},reconstructed,provider,'installer.exe');
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
  if(!(await fs.readFile(reconstructed)).equals(newBytes))throw Error('Reconstructed installer differs');
  const installDir=path.join(root,'安装 空格验收'),sentinel=path.join(root,'用户资料.txt');
  await fs.writeFile(sentinel,'保留材料');
  await run(old.exe,['/S',`/D=${installDir}`]);
  if(await fs.readFile(path.join(installDir,'中文资料.txt'),'utf8')!=='独立安装验收 0.2.3')throw Error('Initial install failed');
  await run(reconstructed,['/S',`/D=${installDir}`]);
  if(await fs.readFile(path.join(installDir,'中文资料.txt'),'utf8')!=='独立安装验收 0.2.4')throw Error('Upgrade failed');
  if(await fs.readFile(sentinel,'utf8')!=='保留材料')throw Error('User sentinel modified');
  const report={fullBytes:info.size,downloadBytes:transferred,savedPercent:100*(1-transferred/info.size),rangeRequests:ranges,realNsisReconstruction:true,chineseAndSpacePath:true,installedOldThenReconstructedNew:true,externalDataRetained:true,scope:'Isolated minimal NSIS fixtures, not full production installation'};
  await fs.writeFile(path.join(root,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
  const uninstaller=(await fs.readdir(installDir)).find(name=>/^Uninstall.*\.exe$/i.test(name));
  if(uninstaller)await run(path.join(installDir,uninstaller),['/S']);
}
main().catch(error=>{console.error(error);process.exitCode=1});
