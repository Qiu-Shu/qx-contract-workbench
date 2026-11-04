// Actual NSIS packages with an isolated app identity. Never uses the user's app/data.
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
const {build}=require('D:/qx-contract-workbench-20261102/desktop/node_modules/electron-builder');
const {prepareIncrementalPackage}=require('./incremental-package.cjs');
const {customizeInstaller}=require('./installer-customize.cjs');
const ROOT=path.resolve(__dirname,'..');
const nodeExe='C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe';
const sevenZip='C:/Users/Lenovo/AppData/Local/electron-builder/Cache/7zip@1.0.0/7zip-win-x64-a34pt/bin/7za.exe';
const templates='D:/qx-contract-workbench-20261102/desktop/node_modules/app-builder-lib/templates/nsis';
async function run(file,args){const start=Date.now();await new Promise((resolve,reject)=>{const c=spawn(file,args,{windowsHide:true,stdio:'ignore'});c.once('error',reject);c.once('close',code=>code===0?resolve():reject(Error(path.basename(file)+' exited '+code)))});return (Date.now()-start)/1000;}
async function main(){
  const out=path.join(ROOT,'.local/install-speed-check/nsis-'+Date.now());await fs.mkdir(out,{recursive:true});
  const app=path.join(out,'app');await fs.mkdir(app);
  const oldDir=path.join(out,'old'),newDir=path.join(out,'next');
  for(const dir of [oldDir,newDir]){
    await fs.mkdir(path.join(dir,'resources/workbench/runtime'),{recursive:true});
    await fs.copyFile(nodeExe,path.join(dir,'resources/workbench/runtime/node.exe'));
    await fs.copyFile('C:/Windows/System32/where.exe',path.join(dir,'QunxingInstallQa.exe'));
    await fs.copyFile('C:/Windows/System32/where.exe',path.join(dir,'QunxingWorkbench.exe'));
    await fs.mkdir(path.join(dir,'unchanged'));
    for(let i=0;i<180;i++)await fs.writeFile(path.join(dir,'unchanged',i+'.txt'),'unchanged fixture '+i);
  }
  await fs.writeFile(path.join(oldDir,'resources/app.asar'),'old synthetic application');
  await fs.writeFile(path.join(newDir,'resources/app.asar'),'new synthetic application');
  await fs.writeFile(path.join(oldDir,'remove.txt'),'obsolete');
  await fs.writeFile(path.join(newDir,'新增 空格.txt'),'added');
  const delta=await prepareIncrementalPackage({oldDir,newDir,fromVersion:'0.2.6',toVersion:'0.2.7',output:path.join(out,'delta'),toolsDir:path.join(ROOT,'.local/install-speed-check/hdiff-proof/vendor-v5.1.3/windows64')});
  const include=await customizeInstaller({output:path.join(out,'nsis-includes'),templates,incremental:delta,sevenZip,sevenZipLicense:path.resolve(sevenZip,'../../LICENSE.txt')});
  const files=[];
  for(const [version,payload] of [['0.2.6',oldDir],['0.2.7',newDir]]){
    await fs.writeFile(path.join(app,'package.json'),JSON.stringify({name:'qunxing-install-speed-qa',version,main:'index.cjs',author:'QA',description:'Isolated installer verification'}));
    const output=path.join(out,version);
    await build({publish:'never',projectDir:app,prepackaged:payload,config:{appId:'cn.qunxing.install-speed-qa.20261104',productName:'QunxingInstallQa',electronVersion:'44.8.0',npmRebuild:false,compression:'normal',directories:{output},
      win:{executableName:'QunxingInstallQa',target:[{target:'nsis',arch:['x64']}],signAndEditExecutable:false,artifactName:'Qa-${version}.${ext}'},
      nsis:{oneClick:version==='0.2.6',perMachine:false,allowElevation:false,allowToChangeInstallationDirectory:version!=='0.2.6',runAfterFinish:false,createDesktopShortcut:false,createStartMenuShortcut:false,differentialPackage:true,useZip:false,...(version==='0.2.7'?{include}:{} )}}});
    files.push(path.join(output,'Qa-'+version+'.exe'));
  }
  const installDir=path.join(out,'安装路径 含空格');
  const fullSeconds=await run(files[0],['/S','/D='+installDir]);
  await fs.writeFile(path.join(installDir,'用户自加文件.txt'),'keep me');
  const retained=path.join(installDir,'resources/workbench/runtime/node.exe');const before=await fs.stat(retained,{bigint:true});
  const incrementalSeconds=await run(files[1],['--updated','/S','/D='+installDir]);
  const after=await fs.stat(retained,{bigint:true});
  assert.equal(before.ino,after.ino);assert.equal(before.mtimeNs,after.mtimeNs);
  assert.equal(await fs.readFile(path.join(installDir,'resources/app.asar'),'utf8'),'new synthetic application');
  assert.equal(await fs.readFile(path.join(installDir,'新增 空格.txt'),'utf8'),'added');
  assert.equal(await fs.readFile(path.join(installDir,'用户自加文件.txt'),'utf8'),'keep me');
  await assert.rejects(fs.access(path.join(installDir,'remove.txt')));
  const report={passed:true,fullSeconds,incrementalSeconds,unchangedRuntimeFileIdentityAndMtimePreserved:true,unmanagedFilePreserved:true,changedAddedDeletedVerified:true,installDir,installer:files[1],stats:delta.stats};
  await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
  await fs.writeFile(path.join(ROOT,'.local/install-speed-check/latest-nsis-test.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
}
main().catch(error=>{console.error(error);process.exit(1)});
