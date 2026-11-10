const {createRequire}=require('node:module');
const {CancellationToken}=createRequire(require.resolve('electron-updater'))('builder-util-runtime');
const {verifyRelease,verifyInstaller}=require('./update-integrity.cjs');
function newer(a,b){const x=a.split('.').map(Number),y=b.split('.').map(Number);for(let i=0;i<3;i++){if(x[i]!==y[i])return x[i]>y[i]}return false;}
function message(error,action){
  if(error?.message==='UPDATE_SIGNATURE')return '更新校验未通过，已停止。当前版本仍可使用，请稍后重试。';
  if(error?.code==='ERR_CHECKSUM_MISMATCH')return '下载文件校验未通过，已停止安装。请重试下载，当前版本和资料仍保留。';
  if(error?.code==='ENOSPC')return '更新缓存所在磁盘空间不足，请释放空间后重试。当前版本和资料仍保留。';
  if(['EACCES','EPERM','EROFS'].includes(error?.code))return '无法写入更新缓存，请检查文件权限或是否被其他程序占用后重试。';
  if(action==='install')return '安装未能开始，请确认任务已结束后重试。当前版本和资料仍保留。';
  if(action==='download')return '更新下载未完成，请检查连接后重试，也可从正式发布页下载安装包。当前版本和资料仍保留。';
  return '暂时无法检查更新，请检查网络后重试。当前版本仍可使用。';
}
function createInstallHandoff({isStarting,setStarting,stop,restore}){
  let acquired=false;
  return {
    async prepare(){
      if(isStarting())throw Error('Settings are changing');
      acquired=true;setStarting(true);await stop();
    },
    async recover(){
      if(!acquired)return;
      try{await restore()}finally{acquired=false;setStarting(false)}
    },
  };
}
function createUpdateController({updater,version,publicKey,prepareInstall,confirmInstall,recoverInstall=async()=>{},onState=()=>{}}){
  let state={phase:'idle',version,availableVersion:null,notes:'',ready:false,progress:0,transferred:0,total:0,error:''};
  let info=null,file=null,busy=false,cancellation=null,cancelled=false;
  updater.autoDownload=false;updater.autoInstallOnAppQuit=false;
  updater.allowDowngrade=false;updater.allowPrerelease=false;updater.disableDifferentialDownload=false;updater.disableWebInstaller=true;
  updater.logger=null;
  const snapshot=()=>({...state});
  const set=patch=>{state={...state,...patch};onState(snapshot());};
  // Download/check promise catches own the UI errors; never forward upstream URLs or credentials.
  updater.on('error',()=>{});
  updater.on('download-progress',progress=>{if(state.phase==='downloading')set({progress:Math.max(0,Math.min(100,progress.percent||0)),transferred:progress.transferred||0,total:progress.total||0});});
  updater.on('qx-delta-plan',plan=>set({downloadMode:'delta',total:plan.downloadBytes,fullSize:plan.fullBytes}));
  updater.on('qx-download-mode',({mode,total})=>{if(state.phase==='downloading')set({downloadMode:mode,total,progress:0,transferred:0});});
  const controller={state:snapshot,
    async check(){
      if(busy||file)return snapshot();busy=true;set({phase:'checking',error:''});info=null;
      try{
        const result=await updater.checkForUpdates();
        if(!result?.updateInfo||!newer(result.updateInfo.version,version)){set({phase:'idle',availableVersion:null});return snapshot();}
        verifyRelease(result.updateInfo,publicKey);info=structuredClone(result.updateInfo);
        set({phase:'available',availableVersion:info.version,notes:info.releaseNotes,ready:false});
      }catch(error){set({phase:'error',availableVersion:null,error:message(error,'check')});}
      finally{busy=false;}return snapshot();
    },
    async download(){
      if(busy||!info||file)return snapshot();busy=true;cancelled=false;cancellation=new CancellationToken();
      set({phase:'downloading',downloadMode:'delta',progress:0,transferred:0,total:0,error:''});
      try{
        verifyRelease(info,publicKey);
        const paths=await updater.downloadUpdate(cancellation);
        if(cancelled){set({phase:'available'});return snapshot();}
        await verifyInstaller(paths[0],info,publicKey);
        if(cancelled){set({phase:'available'});return snapshot();}
        file=paths[0];set({phase:'downloaded',ready:true,progress:100});
      }catch(error){set(cancelled?{phase:'available',error:''}:{phase:'error',error:message(error,'download')});}
      finally{busy=false;cancellation=null;}return snapshot();
    },
    cancel(){if(cancellation){cancelled=true;set({phase:'cancelling'});cancellation.cancel();}return snapshot();},
    async install(){
      if(busy||!file||!info)return snapshot();busy=true;set({phase:'confirming',error:''});
      let prepared=false;
      try{
        if(!await confirmInstall()){set({phase:'downloaded'});return snapshot();}
        await verifyInstaller(file,info,publicKey);
        set({phase:'installing'});prepared=true;await prepareInstall();
        await updater.quitAndInstall(false,true);
      }catch(error){
        if(prepared)try{await recoverInstall()}catch{}
        set({phase:'error',error:message(error,'install')});
      }
      finally{if(state.phase!=='installing')busy=false;}return snapshot();
    },
  };return controller;
}
module.exports={createUpdateController,createInstallHandoff};
