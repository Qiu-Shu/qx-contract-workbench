// Uses only the isolated QA identity produced by check-incremental-installer.cjs.
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const root=path.resolve(process.env.QX_INSTALL_TEST_ROOT||path.join(__dirname,'../.local/install-speed-check'));
async function run(file,args){const start=Date.now();await new Promise((resolve,reject)=>{const child=spawn(file,args,{windowsHide:true,windowsVerbatimArguments:true,stdio:'ignore'});child.once('error',reject);child.once('close',code=>code===0?resolve():reject(Error(path.basename(file)+' exited '+code)))});return(Date.now()-start)/1000;}
async function main(){
  const previous=JSON.parse(await fs.readFile(path.join(root,'latest-nsis-test.json'),'utf8'));
  const prior=path.resolve(previous.installDir);
  assert.ok(prior.startsWith(root+path.sep));
  const uninstaller=path.join(prior,'Uninstall QunxingInstallQa.exe');
  await fs.access(uninstaller);
  await run(uninstaller,['/S','_?='+prior]);
  const installDir=path.join(path.dirname(prior),'首次安装 自选目录');
  await assert.rejects(fs.access(installDir));
  const seconds=await run(previous.installer,['/S','/D='+installDir]);
  assert.equal(await fs.readFile(path.join(installDir,'resources/app.asar'),'utf8'),'new synthetic application');
  assert.equal(await fs.readFile(path.join(installDir,'新增 空格.txt'),'utf8'),'added');
  await fs.access(path.join(installDir,'resources/workbench/runtime/node.exe'));
  await fs.access(path.join(installDir,'Uninstall QunxingInstallQa.exe'));
  await fs.access(path.join(installDir,'resources/7zip-LICENSE.txt'));
  await assert.rejects(fs.access(path.join(installDir,'remove.txt')));
  const report={passed:true,seconds,installDir,customDirectoryWithChineseAndSpaces:true,newInstallerFreshExtractVerified:true};
  await fs.writeFile(path.join(root,'fresh-install-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
}
main().catch(error=>{console.error(error);process.exit(1)});
