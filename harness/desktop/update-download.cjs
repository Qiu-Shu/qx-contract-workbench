const fs=require('node:fs/promises');
const path=require('node:path');
const {gunzipSync,gzipSync}=require('node:zlib');
const {NsisUpdater}=require('electron-updater');
const {GenericDifferentialDownloader}=require('electron-updater/out/differentialDownloader/GenericDifferentialDownloader');
const {computeOperations,OperationKind}=require('electron-updater/out/differentialDownloader/downloadPlanBuilder');
const {createRequire}=require('node:module');
const {configureRequestOptionsFromUrl,DigestTransform,ProgressCallbackTransform,CancellationError}=createRequire(require.resolve('electron-updater'))('builder-util-runtime');
const {pipeline}=require('node:stream/promises');
async function downloadFull(executor,url,destination,options){
  const token=options.cancellationToken,abort=new AbortController();
  let request,response,complete=false,redirects=0;
  const cancel=()=>abort.abort(new CancellationError());
  if(token.cancelled)throw new CancellationError();
  token.once('cancel',cancel);
  try{
    response=await new Promise((resolve,reject)=>{
      const fail=error=>{abort.abort(error);reject(error);};
      request=executor.createRequest(configureRequestOptionsFromUrl(url,{headers:options.headers,redirect:'manual'}),resolve);
      abort.signal.addEventListener('abort',()=>{request.abort?.();reject(abort.signal.reason);},{once:true});
      request.on('redirect',(_status,_method,target)=>{
        try{if(++redirects>10||(url.protocol==='https:'&&new URL(target).protocol!=='https:'))throw Error('UPDATE_REDIRECT');request.followRedirect();}catch(error){fail(error)}
      });
      executor.addErrorAndTimeoutHandlers(request,fail);request.end();
    });
    if(response.statusCode!==200)throw Error('UPDATE_HTTP_'+response.statusCode);
    const streams=[response];
    const length=Number(response.headers['content-length']);
    if(options.onProgress&&Number.isSafeInteger(length)&&length>0)streams.push(new ProgressCallbackTransform(length,token,options.onProgress));
    streams.push(new DigestTransform(options.sha512),require('node:fs').createWriteStream(destination));
    // pipeline destroys and waits for every stream, including the file, on cancellation.
    await pipeline(...streams,{signal:abort.signal});complete=true;
    return destination;
  }catch(error){if(token.cancelled)throw new CancellationError();throw error;}
  finally{token.removeListener('cancel',cancel);if(!complete){request?.abort?.();response?.destroy?.();}}
}
function deltaPlan(oldMap,newMap,size,logger){
  if(oldMap.version!==newMap.version)throw Error('UPDATE_DELTA_ONLY');
  const tasks=computeOperations(oldMap,newMap,logger);
  const downloadBytes=tasks.filter(t=>t.kind===OperationKind.DOWNLOAD).reduce((n,t)=>n+t.end-t.start,0);
  const copyBytes=tasks.filter(t=>t.kind===OperationKind.COPY).reduce((n,t)=>n+t.end-t.start,0);
  if(copyBytes<=0||downloadBytes>=size||downloadBytes+copyBytes!==size)throw Error('UPDATE_DELTA_ONLY');
  return {downloadBytes,copyBytes,fullBytes:size};
}
// The upstream single-range downloader accepts HTTP 200. Refuse it before piping a full response.
const cancellationScope=Symbol('qx-download-cancellation');
function rangeOnlyExecutor(executor,token){
  if(executor[cancellationScope]===token)return executor;
  return new Proxy(executor,{get(target,key,receiver){
    if(key===cancellationScope)return token;
    if(key==='download')return (url,destination,options)=>downloadFull(target,url,destination,options);
    if(key==='createRequest')return (options,callback)=>{
      let request,activeResponse;
      const cleanup=()=>token?.removeListener('cancel',cancel);
      const cancel=()=>{cleanup();request.abort?.();activeResponse?.destroy?.();request.emit('error',Error('cancelled'));};
      request=target.createRequest(options,response=>{
        activeResponse=response;response.once('end',cleanup);response.once('close',cleanup);
        if(response.statusCode>=400||(options.headers?.range&&response.statusCode!==206)){
          cleanup();request.abort?.();response.destroy?.();
          request.emit('error',Error(options.headers?.range?'UPDATE_DELTA_ONLY':'UPDATE_HTTP_'+response.statusCode));return;
        }
        callback(response);
      });
      request.once('close',cleanup);request.once('error',cleanup);
      // Defer an already-cancelled token until upstream has attached its error handler.
      if(token?.cancelled)queueMicrotask(cancel);else token?.once('cancel',cancel);
      return request;
    };
    const value=Reflect.get(target,key,receiver);return typeof value==='function'?value.bind(receiver):value;
  }});
}
class StrictNsisUpdater extends NsisUpdater{
  async doDownloadUpdate(options){
    const executor=this.httpExecutor;
    // The upstream full downloader rejects cancellation without aborting the request.
    this.httpExecutor=rangeOnlyExecutor(executor,options.cancellationToken);
    try{return await super.doDownloadUpdate(options)}finally{this.httpExecutor=executor}
  }
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
    try{await fs.access(oldFile)}catch(error){if(error.code==='ENOENT')throw Error('UPDATE_DELTA_ONLY');throw error;}
    const urls=await provider.getBlockMapFiles(fileInfo.url,this.app.version,options.updateInfoAndProvider.info.version,this.previousBlockmapBaseUrlOverride);
    const readMap=async url=>{
      const buffer=await this.httpExecutor.downloadToBuffer(url,{headers:options.requestHeaders,cancellationToken:options.cancellationToken});
      return JSON.parse(gunzipSync(buffer,{maxOutputLength:16*1024*1024}).toString('utf8'));
    };
    // Fetch the map for the installed version, not a map overwritten by a pending update.
    // Keep map requests sequential so a failed map cannot leave a sibling downloading.
    const oldMap=await readMap(urls[0]),newMap=await readMap(urls[1]);
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
