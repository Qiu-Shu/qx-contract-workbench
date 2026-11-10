const path=require('node:path');
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const {load,packageDir,sevenZip}=require('./toolchain.cjs');
if(!process.argv[2])throw Error('Use build.cjs <stage-directory> [output-directory]; run stage.cjs first');
const stage=path.resolve(process.argv[2]);
const output=path.resolve(process.argv[3]||path.join(stage,'dist'));
const shim=path.join(stage,'build-tools');fs.mkdirSync(shim,{recursive:true});
process.env.PATH=shim+path.delimiter+path.dirname(process.execPath)+path.delimiter+process.env.PATH;
process.env.ELECTRON_BUILDER_COMPRESSION_LEVEL??='1';
const packageInfo=JSON.parse(fs.readFileSync(path.join(stage,'app/package.json'),'utf8'));
const existingArchive=path.join(output,`${packageInfo.name}-${packageInfo.version}-x64.nsis.7z`);
if(fs.existsSync(existingArchive))throw Error('A previous archive cache exists. Use a new output directory to avoid packaging stale or interrupted files.');
const {build}=load('electron-builder');
const {prepareIncrementalPackage,inventory}=require('./incremental-package.cjs');
const {customizeInstaller}=require('./installer-customize.cjs');
const {ensureHdiffTools}=require('./hdiffpatch-tools.cjs');
const baseDir=path.join(stage,'base');
const baseVersion=require('./bootstrap.lock.json').version;
if(!/^\d+\.\d+\.\d+$/.test(baseVersion||''))throw Error('Invalid pinned bootstrap version');
const prepackaged=path.join(stage,'win-unpacked');
let appOutDir=prepackaged;
const installerInclude=path.join(shim,'nsis','qx-installer-include.nsh');
const thirdParty=path.join(__dirname,'vendor/hdiffpatch');
async function main(){
await require('./verify-stage.cjs').verifyBase(stage);
const SEVEN_ZIP=await sevenZip();
const sevenZipLicense=path.resolve(SEVEN_ZIP,'../../LICENSE.txt');
if(prepackaged){
  fs.cpSync(thirdParty,path.join(prepackaged,'resources/licenses/hdiffpatch'),{recursive:true});
  fs.copyFileSync(sevenZipLicense,path.join(prepackaged,'resources/7zip-LICENSE.txt'));
}
fs.writeFileSync(path.join(stage,'app/package-lock.json'),JSON.stringify({name:packageInfo.name,version:packageInfo.version,lockfileVersion:3,packages:{'':{name:packageInfo.name,version:packageInfo.version}}}));
    // Differential NSIS packages use non-solid 7z archives for reusable blocks.
    const bundled=path.join(appOutDir,'resources/workbench');
    for(const relative of ['bridge/case_memory.py','bridge/case_memory_server.py','plugins/case-memory/index.mjs','desktop-runner/case-memory-runtime.cjs','config/case-memory-requirements.lock']){
      if(!fs.existsSync(path.join(bundled,relative)))throw Error('Required case memory file missing from package: '+relative);
    }
    for(const relative of ['node_modules/@deepseek-ai/dsh/lib/bin.js','node_modules/@deepseek-ai/libreoffice-kit-win32-x64/bin/libreoffice-kit.exe','node_modules/@deepseek-ai/libreoffice-kit-win32-x64/prebuilds.json','node_modules/@qunxing/desktop-session/attachment-preview.mjs','node_modules/@qunxing/desktop-session/client.js','browser/node_modules/bb-browser/dist/cli.js','runtime/python/python.exe','desktop-runner/installed-host.cjs','workspace-seed/AGENTS.md','config/templates/catalog.json','config/contract-0.2.0-defaults.json','plugins/privacy/client.js']){
      if(!fs.existsSync(path.join(bundled,relative)))throw Error('Required runtime file missing from package: '+relative);
    }
    const version=execFileSync(path.join(bundled,'runtime/node.exe'),[path.join(bundled,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'--version'],{cwd:bundled,windowsHide:true,timeout:30000,encoding:'utf8'}).trim();
    if(version!=='0.2.2-alpha.2')throw Error('Bundled Harness failed its startup check');
    execFileSync(path.join(bundled,'runtime/node.exe'),[path.resolve(__dirname,'../scripts/check_office_preview.mjs'),bundled],{windowsHide:true,timeout:30000,stdio:'pipe'});
    console.log('Packaged Node and Harness startup verified.');
    await require('./verify-stage.cjs').verifySources(stage);
    const finalInputs=JSON.stringify([...await inventory(appOutDir)]);

await build({publish:'never',projectDir:path.join(stage,'app'),prepackaged,
  // This hook runs after the final archive inputs are prepared, before NSIS reads
  // its include. The patch must describe those final inputs, including builder files.
  effectiveOptionComputed:async()=>{
    if(!appOutDir)throw Error('Final application tree missing');
    if(JSON.stringify([...await inventory(appOutDir)])!==finalInputs)throw Error('Candidate changed while archiving; use a fresh stage/output and do not run tests inside the candidate during packaging');
    const incremental=await prepareIncrementalPackage({oldDir:baseDir,newDir:appOutDir,fromVersion:baseVersion,toVersion:packageInfo.version,output:path.join(output,'incremental'),toolsDir:await ensureHdiffTools(SEVEN_ZIP)});
    await customizeInstaller({output:path.dirname(installerInclude),templates:path.join(packageDir('app-builder-lib'),'templates/nsis'),incremental,sevenZip:SEVEN_ZIP,sevenZipLicense});
    console.log('Changes-only installation package: '+JSON.stringify(incremental.stats));return false;
  },config:{
  appId:'cn.qunxing.harness.workbench',productName:'AI师兄法律助手平台',asar:true,compression:'normal',
  electronVersion:'44.8.0',
  directories:{output},files:['*.cjs','*.html','*.css','*.js','package.json','update-config.json'],
  publish:require('../desktop/update-config.json').feed,
  win:{executableName:'QunxingWorkbench',target:[{target:'nsis',arch:['x64']}],signAndEditExecutable:false,artifactName:'Qunxing-Workbench-${version}-Setup.${ext}'},
  nsis:{oneClick:false,allowToChangeInstallationDirectory:true,allowElevation:false,perMachine:false,deleteAppDataOnUninstall:false,runAfterFinish:true,createDesktopShortcut:true,createStartMenuShortcut:true,include:installerInclude,differentialPackage:true,useZip:false},
  npmRebuild:false,
}}).then(paths=>{
  if(process.env.QX_UPDATE_SIGNING_KEY)require('./update-release.cjs').signManifest(output,fs.readFileSync(path.join(__dirname,'update-notes.txt'),'utf8'));
  else {fs.renameSync(path.join(output,'latest.yml'),path.join(output,'latest.unsigned.yml'));console.log('Manual-install build: no update manifest may be published without the original signing key.');}
  console.log(JSON.stringify(paths));
});
}
main().catch(error=>{console.error(error);process.exitCode=1});
