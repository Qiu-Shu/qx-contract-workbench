// Actual NSIS packages with an isolated app identity. Never uses the user's app/data.
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
const {load,packageDir,sevenZip:resolveSevenZip}=require('./toolchain.cjs');
const {build}=load('electron-builder');
const {prepareIncrementalPackage}=require('./incremental-package.cjs');
const {customizeInstaller}=require('./installer-customize.cjs');
const ROOT=path.resolve(__dirname,'..');
const nodeExe=process.execPath;
const templates=path.join(packageDir('app-builder-lib'),'templates/nsis');
async function run(file,args){const start=Date.now();await new Promise((resolve,reject)=>{const c=spawn(file,args,{windowsHide:true,windowsVerbatimArguments:args.some(arg=>arg.startsWith('_?=')),stdio:'ignore'});c.once('error',reject);c.once('close',code=>code===0?resolve():reject(Error(path.basename(file)+' exited '+code)))});return (Date.now()-start)/1000;}
async function main(){
  const testRoot=path.resolve(process.env.QX_INSTALL_TEST_ROOT||path.join(ROOT,'.local/install-speed-check'));
  const out=path.join(testRoot,'nsis-'+Date.now());await fs.mkdir(out,{recursive:true});
  const sevenZip=await resolveSevenZip();
  const app=path.join(out,'app');await fs.mkdir(app);
  const oldDir=path.join(out,'old'),newDir=path.join(out,'next');
  for(const dir of [oldDir,newDir]){
    await fs.mkdir(path.join(dir,'resources/workbench/runtime'),{recursive:true});
    await fs.copyFile(nodeExe,path.join(dir,'resources/workbench/runtime/node.exe'));
    await fs.copyFile(path.join(process.env.SystemRoot,'System32/where.exe'),path.join(dir,'QunxingInstallQa.exe'));
    await fs.copyFile(path.join(process.env.SystemRoot,'System32/where.exe'),path.join(dir,'QunxingWorkbench.exe'));
    await fs.mkdir(path.join(dir,'unchanged'));
    for(let i=0;i<180;i++)await fs.writeFile(path.join(dir,'unchanged',i+'.txt'),'unchanged fixture '+i);
  }
  await fs.writeFile(path.join(oldDir,'resources/app.asar'),'old synthetic application');
  await fs.writeFile(path.join(newDir,'resources/app.asar'),'new synthetic application');
  await fs.writeFile(path.join(oldDir,'remove.txt'),'obsolete');
  await fs.writeFile(path.join(newDir,'新增 空格.txt'),'added');
  const middleDir=path.join(out,'middle');await fs.cp(oldDir,middleDir,{recursive:true});
  await fs.writeFile(path.join(middleDir,'resources/app.asar'),'middle synthetic application');
  const toolsDir=await require('./hdiffpatch-tools.cjs').ensureHdiffTools(sevenZip);
  const delta=await prepareIncrementalPackage({oldDir,newDir,fromVersion:'0.2.6',toVersion:'0.2.8',output:path.join(out,'delta'),toolsDir});
  const alternate=await prepareIncrementalPackage({oldDir:middleDir,newDir,fromVersion:'0.2.7',toVersion:'0.2.8',output:path.join(out,'alternate'),toolsDir});
  const include=await customizeInstaller({output:path.join(out,'nsis-includes'),templates,incremental:delta,additionalIncrementals:[alternate],sevenZip,sevenZipLicense:path.resolve(sevenZip,'../../LICENSE.txt')});
  const files=[];
  for(const [version,payload] of [['0.2.6',oldDir],['0.2.7',middleDir],['0.2.8',newDir]]){
    await fs.writeFile(path.join(app,'package.json'),JSON.stringify({name:'qunxing-install-speed-qa',version,main:'index.cjs',author:'QA',description:'Isolated installer verification'}));
    const output=path.join(out,version);
    await build({publish:'never',projectDir:app,prepackaged:payload,config:{appId:'cn.qunxing.install-speed-qa.20261104',productName:'QunxingInstallQa',electronVersion:'44.8.0',npmRebuild:false,compression:'normal',directories:{output},
      win:{executableName:'QunxingInstallQa',target:[{target:'nsis',arch:['x64']}],signAndEditExecutable:false,artifactName:'Qa-${version}.${ext}'},
      nsis:{oneClick:version!=='0.2.8',perMachine:false,allowElevation:false,allowToChangeInstallationDirectory:version==='0.2.8',runAfterFinish:false,createDesktopShortcut:false,createStartMenuShortcut:false,differentialPackage:true,useZip:false,...(version==='0.2.8'?{include}:{} )}}});
    files.push(path.join(output,'Qa-'+version+'.exe'));
  }
  const upgrades=[];let installDir;
  for(const [index,source] of files.slice(0,2).entries()){
  installDir=path.join(out,'安装路径 含空格 '+index);
  const fullSeconds=await run(source,['/S','/D='+installDir]);
  await fs.writeFile(path.join(installDir,'用户自加文件.txt'),'keep me');
  const retained=path.join(installDir,'resources/workbench/runtime/node.exe');const before=await fs.stat(retained,{bigint:true});
  const incrementalSeconds=await run(files[2],['--updated','/S','/D='+installDir]);
  const after=await fs.stat(retained,{bigint:true});
  assert.equal(before.ino,after.ino);assert.equal(before.mtimeNs,after.mtimeNs);
  assert.equal(await fs.readFile(path.join(installDir,'resources/app.asar'),'utf8'),'new synthetic application');
  assert.equal(await fs.readFile(path.join(installDir,'新增 空格.txt'),'utf8'),'added');
  assert.equal(await fs.readFile(path.join(installDir,'用户自加文件.txt'),'utf8'),'keep me');
  await assert.rejects(fs.access(path.join(installDir,'remove.txt')));
  upgrades.push({from:index===0?'0.2.6':'0.2.7',to:'0.2.8',fullSeconds,incrementalSeconds});
  if(index===0)await run(path.join(installDir,'Uninstall QunxingInstallQa.exe'),['/S','_?='+installDir]);
  }
  const report={passed:true,upgrades,unchangedRuntimeFileIdentityAndMtimePreserved:true,unmanagedFilePreserved:true,changedAddedDeletedVerified:true,installDir,installer:files[2],stats:delta.stats};
  await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
  await fs.writeFile(path.join(testRoot,'latest-nsis-test.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
}
main().catch(error=>{console.error(error);process.exit(1)});
