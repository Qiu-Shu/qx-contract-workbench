const fs=require('node:fs');
const path=require('node:path');
const {createRequire}=require('node:module');
const {gunzipSync}=require('node:zlib');
const {verifyRelease,verifyInstaller}=require('../desktop/update-integrity.cjs');
const {deltaPlan}=require('../desktop/update-download.cjs');
const yaml=createRequire(require.resolve('electron-updater'))('js-yaml');
const asar=require('D:/qx-contract-workbench-20261102/desktop/node_modules/@electron/asar');
async function main(){
  const dir=path.resolve(process.argv[2]),root=path.resolve(__dirname,'..');
  const config=require('../desktop/update-config.json');
  const info=yaml.load(fs.readFileSync(path.join(dir,'latest.yml'),'utf8'));
  verifyRelease(info,config.publicKey);await verifyInstaller(path.join(dir,info.files[0].url),info,config.publicKey);
  const archive=path.join(dir,'win-unpacked/resources/app.asar');
  const list=asar.listPackage(archive);
  if(list.some(name=>/update-signing-key|\.qx-private|\.test\.cjs$|check[_-]/.test(name)))throw Error('Unexpected private/test shell file');
  for(const file of ['installed.cjs','main.cjs','preload.cjs','updates.cjs','update-download.cjs','update-integrity.cjs','update-config.json']){
    if(!asar.extractFile(archive,file).equals(fs.readFileSync(path.join(root,'desktop',file))))throw Error('Stale packaged file '+file);
  }
  if(!fs.readFileSync(path.join(dir,'win-unpacked/resources/workbench/node_modules/@qunxing/desktop-session/client.js')).equals(fs.readFileSync(path.join(root,'desktop/integration/client.js'))))throw Error('Stale packaged sidebar');
  const packageInfo=JSON.parse(asar.extractFile(archive,'package.json'));
  if(packageInfo.version!==info.version||packageInfo.dependencies['electron-updater']!=='6.8.11')throw Error('Version/dependency mismatch');
  const feed=yaml.load(fs.readFileSync(path.join(dir,'win-unpacked/resources/app-update.yml'),'utf8'));
  if(feed.provider!=='github'||feed.owner!=='Qiu-Shu'||feed.repo!=='qx-contract-workbench'||feed.updaterCacheDirName!=='qunxing-harness-desktop-updater')throw Error('Wrong published feed/cache identity');
  const map=file=>JSON.parse(gunzipSync(fs.readFileSync(file)));
  const newMap=map(path.join(dir,info.files[0].url+'.blockmap'));
  const report={version:info.version,size:info.files[0].size,signatureVerified:true,installerHashVerified:true,packagedSourcesMatch:true,githubFeedAndCacheVerified:true,noPrivateOrTestShellFiles:true};
  if(process.argv[3]){
    const previous=path.resolve(process.argv[3]);
    const logger={info(){},warn(){},error(){}};
    report.candidateDelta=deltaPlan(map(path.join(previous,info.files[0].url+'.blockmap')),newMap,info.files[0].size,logger);
    report.candidateDelta.note='Same-version production candidates before and after review fixes; not a published cross-version upgrade.';
  }
  fs.writeFileSync(path.join(root,'.local/update-checks/release-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
}
main().catch(error=>{console.error(error.message);process.exitCode=1});
