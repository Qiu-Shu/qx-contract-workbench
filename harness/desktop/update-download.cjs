const fs=require('node:fs/promises');
const path=require('node:path');
const {gunzipSync,gzipSync}=require('node:zlib');
const {NsisUpdater}=require('electron-updater');
const {GenericDifferentialDownloader}=require('electron-updater/out/differentialDownloader/GenericDifferentialDownloader');
const {computeOperations,OperationKind}=require('electron-updater/out/differentialDownloader/downloadPlanBuilder');
function deltaPlan(oldMap,newMap,size,logger){
  if(oldMap.version!==newMap.version)throw Error('UPDATE_DELTA_ONLY');
  const tasks=computeOperations(oldMap,newMap,logger);
  const downloadBytes=tasks.filter(t=>t.kind===OperationKind.DOWNLOAD).reduce((n,t)=>n+t.end-t.start,0);
  const copyBytes=tasks.filter(t=>t.kind===OperationKind.COPY).reduce((n,t)=>n+t.end-t.start,0);
  if(copyBytes<=0||downloadBytes>=size||downloadBytes+copyBytes!==size)throw Error('UPDATE_DELTA_ONLY');
  return {downloadBytes,copyBytes,fullBytes:size};
}
// The upstream single-range downloader accepts HTTP 200. Refuse it before piping a full response.
function rangeOnlyExecutor(executor,token){
  return new Proxy(executor,{get(target,key){
    if(key==='createRequest')return (options,callback)=>{
      let request,activeResponse;
      const cleanup=()=>token?.removeListener('cancel',cancel);
      const cancel=()=>{cleanup();request.emit('error',Error('cancelled'));request.abort?.();activeResponse?.destroy?.();};
      request=target.createRequest(options,response=>{
        activeResponse=response;response.once('end',cleanup);response.once('close',cleanup);
        if(options.headers?.range&&response.statusCode!==206){
          request.emit('error',Error('UPDATE_DELTA_ONLY'));request.abort?.();response.destroy?.();return;
        }
        callback(response);
      });
      request.once('close',cleanup);request.once('error',cleanup);
      // Defer an already-cancelled token until upstream has attached its error handler.
      if(token?.cancelled)queueMicrotask(cancel);else token?.once('cancel',cancel);
      return request;
    };
    const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
  }});
}
class StrictNsisUpdater extends NsisUpdater{
  // This product installs per-user. Wait for a successful process launch before quitting.
  // Upstream NSIS returns immediately and may quit even when Windows rejects the EXE.
  async quitAndInstall(isSilent=false,isForceRunAfter=true){
    if(!this.installerPath)throw Error('UPDATE_INSTALLER_MISSING');
    const args=['--updated'];if(isSilent)args.push('/S');if(isForceRunAfter)args.push('--force-run');
    await new Promise((resolve,reject)=>{
      const child=require('node:child_process').spawn(this.installerPath,args,{detached:true,stdio:'ignore',windowsHide:true});
      child.once('error',reject);child.once('spawn',()=>{child.unref();resolve()});
    });
    this.app.quit();
  }
  async differentialDownloadInstaller(fileInfo,options,installerPath,provider,oldName){
    for(let attempt=0;attempt<2;attempt++){
      try{return await this.downloadDelta(fileInfo,options,installerPath,provider,oldName)}
      catch(error){
        if(options.cancellationToken.cancelled||['ENOSPC','EACCES','EPERM','EROFS'].includes(error.code))throw error;
        // Retry transient transport failures once; an invalid cache/range cannot heal by retrying.
        const transient=/ECONNRESET|ETIMEDOUT|ERR_(?:CONNECTION|NETWORK|TIMED_OUT)|aborted by the server/i.test(error.code||'')||/aborted by the server|net::ERR_(?:CONNECTION|NETWORK|TIMED_OUT)/i.test(error.message||'');
        if(attempt===0&&transient){this.emit('qx-download-mode',{mode:'retry',total:0});continue;}
        // Upstream performs a fresh full download with SHA-512 validation; the controller
        // still checks the signed release before downloading and the bytes before installing.
        this.emit('qx-download-mode',{mode:'full',total:fileInfo.info.size});
        return true;
      }
    }
  }
  async downloadDelta(fileInfo,options,installerPath,provider,oldName){
    const oldFile=path.join(this.downloadedUpdateHelper.cacheDir,oldName);
    try{await fs.access(oldFile)}catch{throw Error('UPDATE_DELTA_ONLY')}
    const urls=await provider.getBlockMapFiles(fileInfo.url,this.app.version,options.updateInfoAndProvider.info.version,this.previousBlockmapBaseUrlOverride);
    const readMap=async url=>{
      const buffer=await this.httpExecutor.downloadToBuffer(url,{headers:options.requestHeaders,cancellationToken:options.cancellationToken});
      return JSON.parse(gunzipSync(buffer,{maxOutputLength:16*1024*1024}).toString('utf8'));
    };
    // Fetch the map for the installed version, not a map overwritten by a pending update.
    const [oldMap,newMap]=await Promise.all(urls.map(readMap));
    const plan=deltaPlan(oldMap,newMap,fileInfo.info.size,this._logger);
    this.emit('qx-delta-plan',plan);
    await new GenericDifferentialDownloader(fileInfo.info,rangeOnlyExecutor(this.httpExecutor,options.cancellationToken),{
      newUrl:fileInfo.url,oldFile,newFile:installerPath,logger:this._logger,isUseMultipleRangeRequest:false,
      requestHeaders:options.requestHeaders,cancellationToken:options.cancellationToken,
      onProgress:progress=>this.emit('download-progress',progress),
    }).download(oldMap,newMap);
    await fs.writeFile(path.join(this.downloadedUpdateHelper.cacheDirForPendingUpdate,'current.blockmap'),gzipSync(JSON.stringify(newMap)));
    return false;
  }
}
function validateFeed(feed){
  if(feed?.provider==='github'&&feed.owner==='Qiu-Shu'&&feed.repo==='qx-contract-workbench'&&!feed.token&&!feed.private)return feed;
  if(feed?.provider==='generic'){
    const url=new URL(feed.url);
    if(url.protocol==='https:'&&!url.username&&!url.password&&!url.search&&!url.hash)return {provider:'generic',url:url.href,useMultipleRangeRequest:false};
  }
  throw Error('UPDATE_SOURCE_INVALID');
}
module.exports={StrictNsisUpdater,deltaPlan,rangeOnlyExecutor,validateFeed};
