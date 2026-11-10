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
  const payload=path.join(candidate,'resources/workbench'),app=path.join(stage,'app'),asar=load('@electron/asar');
  asar.extractAll(path.join(base,'resources/app.asar'),app);
  const manifest=[];
  for(const folder of ['bridge','plugins','legacy','workspace-seed'])overlay(path.join(root,folder),path.join(payload,folder),manifest,'resources/workbench/'+folder);
  overlay(path.join(__dirname,'payload-config'),path.join(payload,'config'),manifest,'resources/workbench/config');
  overlay(path.join(__dirname,'runtime-overrides'),path.join(payload,'node_modules'),manifest,'resources/workbench/node_modules');
  for(const name of ['component-install.py','python-tool.py'])copySource(path.join(__dirname,name),path.join(payload,name),'resources/workbench/'+name,manifest);
  const runner=path.join(payload,'desktop-runner');
  for(const name of fs.readdirSync(runner))if(fs.existsSync(path.join(root,'desktop',name)))copySource(path.join(root,'desktop',name),path.join(runner,name),'resources/workbench/desktop-runner/'+name,manifest);
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
    {target:'resources/workbench/config/initialization.json',sha256:await digest(path.join(payload,'config/initialization.json'))},
    {target:'resources/app.asar',sha256:await digest(path.join(candidate,'resources/app.asar'))},
  ];
  fs.writeFileSync(path.join(stage,'source-manifest.json'),JSON.stringify({version:require('./app-template.json').version,bootstrap:lock,files:manifest,generated},null,2)+'\n');
  console.log(JSON.stringify({stage,base,candidate,sourceFiles:manifest.length}));
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1});
module.exports={overlay,digest};
