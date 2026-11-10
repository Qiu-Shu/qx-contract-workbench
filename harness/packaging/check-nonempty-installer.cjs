// Run after check-fresh-installer.cjs; uses the same isolated QA identity only.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const root=path.resolve(process.env.QX_INSTALL_TEST_ROOT||path.join(__dirname,'../.local/install-speed-check'));
const run=(exe,args)=>new Promise((resolve,reject)=>{const child=spawn(exe,args,{windowsHide:true,windowsVerbatimArguments:true,stdio:'ignore'});child.once('error',reject);child.once('exit',resolve);});
async function main(){
  const fresh=JSON.parse(fs.readFileSync(path.join(root,'fresh-install-report.json'))),prior=path.resolve(fresh.installDir);
  assert.ok(prior.startsWith(root+path.sep));
  assert.equal(await run(path.join(prior,'Uninstall QunxingInstallQa.exe'),['/S','_?='+prior]),0);
  const previous=JSON.parse(fs.readFileSync(path.join(root,'latest-nsis-test.json')));
  const target=path.join(root,'非空保护 '+Date.now());fs.mkdirSync(target);fs.writeFileSync(path.join(target,'保留资料.txt'),'synthetic user file');
  assert.equal(await run(previous.installer,['/S','/D='+target]),1);
  assert.deepEqual(fs.readdirSync(target),['保留资料.txt']);
  assert.equal(fs.readFileSync(path.join(target,'保留资料.txt'),'utf8'),'synthetic user file');
  const report={passed:true,nonemptyFolderRejected:true,existingFileUnchanged:true};
  fs.writeFileSync(path.join(root,'nonempty-install-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}
main().catch(error=>{console.error(error);process.exitCode=1});
