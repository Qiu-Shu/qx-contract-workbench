// Immutable published bootstrap supplies third-party runtimes/dependencies only.
// Every first-party application overlay is sourced from this checkout.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {pipeline}=require('node:stream/promises');
const {execFileSync}=require('node:child_process');
const {load,sevenZip}=require('./toolchain.cjs');
const lock=require('./bootstrap.lock.json');
const root=path.resolve(__dirname,'..');
const digest=file=>new Promise((resolve,reject)=>{const hash=crypto.createHash('sha256');fs.createReadStream(file).on('data',chunk=>hash.update(chunk)).on('error',reject).on('end',()=>resolve(hash.digest('hex')));});
async function download(url,file,sha){
  if(!fs.existsSync(file)){const response=await fetch(url,{signal:AbortSignal.timeout(600000)});if(!response.ok)throw Error('Download failed: '+response.status);await pipeline(response.body,fs.createWriteStream(file,{flags:'wx'}));}
  if(await digest(file)!==sha)throw Error('Bootstrap checksum mismatch: '+path.basename(file));
}
const excluded=name=>['node_modules','.git','.local','__pycache__','tests'].includes(name)||/\.(test\.(?:mjs|cjs|js)|pyc|pyo|log)$/.test(name);
function overlay(source,target,manifest,relative=''){
  for(const entry of fs.readdirSync(source,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
    if(excluded(entry.name))continue;
    if(entry.isSymbolicLink())throw Error('Source links are not distributable');
    const from=path.join(source,entry.name),to=path.join(target,entry.name),name=relative?relative+'/'+entry.name:entry.name;
    if(entry.isDirectory()){fs.mkdirSync(to,{recursive:true});overlay(from,to,manifest,name);}
    else if(entry.isFile()){fs.copyFileSync(from,to);manifest.push({source:path.relative(root,from).split(path.sep).join('/'),target:name,sha256:crypto.createHash('sha256').update(fs.readFileSync(from)).digest('hex')});}
  }
}
function copySource(from,to,target,manifest){
  fs.copyFileSync(from,to);
  manifest.push({source:path.relative(root,from).split(path.sep).join('/'),target,sha256:crypto.createHash('sha256').update(fs.readFileSync(from)).digest('hex')});
}
function copyBackupConfiguration(sourceRoot,payload,manifest){
  fs.mkdirSync(path.join(payload,'config'),{recursive:true});
  for(const name of ['backup-settings.json','postgres-backup-runtime.json'])
    copySource(path.join(sourceRoot,'config',name),path.join(payload,'config',name),'resources/workbench/config/'+name,manifest);
}
function copyDesktopRunners(sourceRoot,payload,manifest){
  const runner=path.join(payload,'desktop-runner');
  fs.mkdirSync(runner,{recursive:true});
  for(const name of ['case-memory-runtime.cjs','host-recovery.cjs','installed-host.cjs','installed-migrations.cjs',
    'installed-runtime.cjs','installed-stop.cjs','stop-installed.cjs','backup-preparation.cjs','local-backup.cjs'])
    copySource(path.join(sourceRoot,'desktop',name),path.join(runner,name),'resources/workbench/desktop-runner/'+name,manifest);
}
function copyMediaRegistry(source,payload,manifest){
  const registry=JSON.parse(fs.readFileSync(source,'utf8')),ids=new Set();
  if(registry.version!==1||!Array.isArray(registry.sources)||!registry.sources.length)throw Error('Invalid media source registry');
  for(const item of registry.sources){
    let url;try{url=new URL(item.url);}catch{throw Error('Invalid media source registry URL');}
    if(typeof item.id!=='string'||!item.id||ids.has(item.id)||typeof item.title!=='string'||!item.title||
      url.protocol!=='https:'||url.username||url.password||!Array.isArray(item.allowed_hosts)||!item.allowed_hosts.includes(url.hostname)||
      !['news','law'].includes(item.source_kind)||!Number.isInteger(item.refresh_minutes)||item.refresh_minutes<=0)throw Error('Invalid media source registry');
    ids.add(item.id);
  }
  fs.mkdirSync(path.join(payload,'sources'),{recursive:true});
  copySource(source,path.join(payload,'sources/media-source-registry.json'),'resources/workbench/sources/media-source-registry.json',manifest);
}
function copySkillLabels(source,payload,manifest){
  const catalog=JSON.parse(fs.readFileSync(source,'utf8'));
  if(catalog.version!==1||!catalog.labels||Array.isArray(catalog.labels)||typeof catalog.labels!=='object'||
    !Object.entries(catalog.labels).every(([id,label])=>/^[a-z0-9-]+$/.test(id)&&typeof label==='string'&&label.trim()))throw Error('Invalid Skill label catalog');
  const relative='node_modules/@deepseek-ai/dsh-client-ui-skill/lib/client.js',file=path.join(payload,relative);
  const original=fs.readFileSync(file,'utf8'),matches=[...original.matchAll(/const qxSkillLabels = (\{[\s\S]*?\});/g)];
  if(matches.length!==1)throw Error('Skill label mapping differs from the pinned UI');
  const labels={...JSON.parse(matches[0][1]),...catalog.labels};
  const updated=original.replace(matches[0][0],()=>'const qxSkillLabels = '+JSON.stringify(labels,null,2)+';');
  fs.mkdirSync(path.join(payload,'config'),{recursive:true});
  copySource(source,path.join(payload,'config/skill-labels.zh-CN.json'),'resources/workbench/config/skill-labels.zh-CN.json',manifest);
  fs.writeFileSync(file,updated);
  return {target:'resources/workbench/'+relative,sha256:crypto.createHash('sha256').update(updated).digest('hex')};
}
function copyContentWatchAssets(payload,manifest){
  for(const relative of ['scripts/prepare-content-watch.mjs','sources/xiaohongshu-mcp-Apache-2.0.txt']){
    const target=path.join(payload,relative);
    fs.mkdirSync(path.dirname(target),{recursive:true});
    copySource(path.join(root,relative),target,'resources/workbench/'+relative,manifest);
  }
}
async function main(){
  if(process.platform!=='win32')throw Error('Windows x64 release staging requires Windows');
  if(!process.argv[2])throw Error('Usage: node stage.cjs <new-stage-directory> [verified-0.2.14-installer]');
  const stage=path.resolve(process.argv[2]);
  if(process.argv[3]==='--refresh'){await refresh(stage);return;}
  if(fs.existsSync(stage))throw Error('Use a new stage directory; existing files are never deleted');
  fs.mkdirSync(stage,{recursive:true});
  const installer=process.argv[3]?path.resolve(process.argv[3]):path.join(stage,'bootstrap.exe');
  await download(lock.url,installer,lock.sha256);
  const archiveTool=path.join(stage,'7zip.exe');await download(lock.sevenZip.url,archiveTool,lock.sevenZip.sha256);
  const tools=path.join(stage,'extractor');
  execFileSync(await sevenZip(),['x',archiveTool,'-o'+tools,'-y','7z.exe','7z.dll'],{windowsHide:true,stdio:'pipe'});
  const seven=path.join(tools,'7z.exe'),container=path.join(stage,'container'),base=path.join(stage,'base');
  execFileSync(seven,['x',installer,'-o'+container,'-y','$PLUGINSDIR/app-64.7z'],{windowsHide:true,stdio:'pipe'});
  execFileSync(seven,['x',path.join(container,'$PLUGINSDIR/app-64.7z'),'-o'+base,'-y','-bso0','-bsp0'],{windowsHide:true,stdio:'pipe'});
  const candidate=path.join(stage,'win-unpacked');fs.cpSync(base,candidate,{recursive:true});
  await refresh(stage);
}
async function refresh(stage){
  const base=path.join(stage,'base'),candidate=path.join(stage,'win-unpacked');
  if(!fs.existsSync(path.join(base,'resources/app.asar'))||!fs.existsSync(path.join(candidate,'resources/workbench/runtime/node.exe')))throw Error('Not a release stage');
  await require('./verify-stage.cjs').verifyBase(stage);
  for(const item of lock.upgradeBases||[]){
    if(!/^\d+\.\d+\.\d+$/.test(item.version))throw Error('Invalid upgrade baseline');
    const destination=path.join(stage,'upgrade-bases',item.version);
    if(!fs.existsSync(destination)){
      const cache=path.resolve(process.env.QX_RELEASE_CACHE||path.join(stage,'downloads'));fs.mkdirSync(cache,{recursive:true});
      const installer=path.join(cache,path.basename(new URL(item.url).pathname));
      await download(item.url,installer,item.sha256);
      const seven=path.join(stage,'extractor/7z.exe'),container=path.join(stage,'upgrade-containers',item.version);
      execFileSync(seven,['x',installer,'-o'+container,'-y','$PLUGINSDIR/app-64.7z'],{windowsHide:true,stdio:'pipe'});
      execFileSync(seven,['x',path.join(container,'$PLUGINSDIR/app-64.7z'),'-o'+destination,'-y','-bso0','-bsp0'],{windowsHide:true,stdio:'pipe'});
    }
  }
  await require('./verify-stage.cjs').verifyUpgradeBases(stage);
  const payload=path.join(candidate,'resources/workbench'),app=path.join(stage,'app'),asar=load('@electron/asar');
  asar.extractAll(path.join(base,'resources/app.asar'),app);
  const manifest=[];
  for(const folder of ['bridge','plugins','legacy','workspace-seed'])overlay(path.join(root,folder),path.join(payload,folder),manifest,'resources/workbench/'+folder);
  copyMediaRegistry(path.join(root,'sources/media-source-registry.json'),payload,manifest);
  overlay(path.join(__dirname,'payload-config'),path.join(payload,'config'),manifest,'resources/workbench/config');
  copyBackupConfiguration(root,payload,manifest);
  overlay(path.join(__dirname,'runtime-overrides'),path.join(payload,'node_modules'),manifest,'resources/workbench/node_modules');
  const skillLabels=copySkillLabels(path.join(root,'config/skill-labels.zh-CN.json'),payload,manifest);
  const toolLabels=require('../scripts/tool-labels.cjs').stageToolLabels(root,payload,manifest);
  for(const name of ['component-install.py','python-tool.py'])copySource(path.join(__dirname,name),path.join(payload,name),'resources/workbench/'+name,manifest);
  copyContentWatchAssets(payload,manifest);
  copyDesktopRunners(root,payload,manifest);
  for(const name of fs.readdirSync(app))if(fs.statSync(path.join(app,name)).isFile()&&fs.existsSync(path.join(root,'desktop',name)))copySource(path.join(root,'desktop',name),path.join(app,name),'app.asar/'+name,manifest);
  copySource(path.join(__dirname,'app-template.json'),path.join(app,'package.json'),'app.asar/package.json',manifest);
  for(const target of ['desktop/integration','node_modules/@qunxing/desktop-session'])overlay(path.join(root,'desktop/integration'),path.join(payload,target),manifest,'resources/workbench/'+target);
  // The initialization identifier is generated from source, never hashed into itself.
  const previousId=manifest.findIndex(item=>item.target==='resources/workbench/config/initialization.json');
  if(previousId>=0)manifest.splice(previousId,1);
  const fingerprint=crypto.createHash('sha256').update(JSON.stringify(manifest)).update(fs.readFileSync(path.join(app,'package.json'))).digest('hex');
  fs.writeFileSync(path.join(payload,'config/initialization.json'),JSON.stringify({schema:1,id:fingerprint})+'\n');
  await asar.createPackage(app,path.join(candidate,'resources/app.asar'));
  const generated=[
    skillLabels,
    toolLabels,
    {target:'resources/workbench/config/initialization.json',sha256:await digest(path.join(payload,'config/initialization.json'))},
    {target:'resources/app.asar',sha256:await digest(path.join(candidate,'resources/app.asar'))},
  ];
  fs.writeFileSync(path.join(stage,'source-manifest.json'),JSON.stringify({version:require('./app-template.json').version,bootstrap:lock,files:manifest,generated},null,2)+'\n');
  console.log(JSON.stringify({stage,base,candidate,sourceFiles:manifest.length}));
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1});
module.exports={overlay,digest,copyMediaRegistry,copySkillLabels,copyBackupConfiguration,copyDesktopRunners,copyContentWatchAssets};
