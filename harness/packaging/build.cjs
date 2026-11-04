const path=require('node:path');
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const stage=path.resolve(process.argv[2]);
const output=path.resolve(process.argv[3]||path.join(stage,'dist'));
const shim=path.join(stage,'build-tools');fs.mkdirSync(shim,{recursive:true});
fs.writeFileSync(path.join(shim,'npm.cmd'),'@"C:\\Users\\Lenovo\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe" "D:\\qx-contract-workbench-20261102\\.local\\desktop-tools\\npm\\package\\bin\\npm-cli.js" %*\r\n');
process.env.PATH=shim+path.delimiter+path.dirname(process.execPath)+path.delimiter+process.env.PATH;
process.env.ELECTRON_BUILDER_COMPRESSION_LEVEL??='1';
const packageInfo=JSON.parse(fs.readFileSync(path.join(stage,'app/package.json'),'utf8'));
const existingArchive=path.join(output,`${packageInfo.name}-${packageInfo.version}-x64.nsis.7z`);
if(fs.existsSync(existingArchive))throw Error('A previous archive cache exists. Use a new output directory to avoid packaging stale or interrupted files.');
const {build}=require('D:/qx-contract-workbench-20261102/desktop/node_modules/electron-builder');
const {prepareIncrementalPackage}=require('./incremental-package.cjs');
const {customizeInstaller}=require('./installer-customize.cjs');
const {ensureHdiffTools,SEVEN_ZIP}=require('./hdiffpatch-tools.cjs');
const baseDir=process.env.QX_BASE_DIR&&path.resolve(process.env.QX_BASE_DIR);
const baseVersion=process.env.QX_BASE_VERSION;
if(!baseDir||!/^\d+\.\d+\.\d+$/.test(baseVersion||''))throw Error('Set QX_BASE_DIR and QX_BASE_VERSION to the verified published installer tree before building an incremental release.');
const prepackaged=process.argv[4]==='--prepackaged'?path.resolve(process.argv[5]||path.join(output,'win-unpacked')):null;
let appOutDir=prepackaged;
const installerInclude=path.join(shim,'nsis','qx-installer-include.nsh');
const thirdParty=path.join(__dirname,'vendor/hdiffpatch');
const sevenZipLicense=path.resolve(SEVEN_ZIP,'../../LICENSE.txt');
if(prepackaged){
  fs.cpSync(thirdParty,path.join(prepackaged,'resources/licenses/hdiffpatch'),{recursive:true});
  fs.copyFileSync(sevenZipLicense,path.join(prepackaged,'resources/7zip-LICENSE.txt'));
}
fs.writeFileSync(path.join(stage,'app/package-lock.json'),JSON.stringify({name:packageInfo.name,version:packageInfo.version,lockfileVersion:3,packages:{'':{name:packageInfo.name,version:packageInfo.version}}}));
build({publish:'never',projectDir:path.join(stage,'app'),...(prepackaged?{prepackaged}:{}),
  // This hook runs after the final archive inputs are prepared, before NSIS reads
  // its include. The patch must describe those final inputs, including builder files.
  effectiveOptionComputed:async()=>{
    if(!appOutDir)throw Error('Final application tree missing');
    const incremental=await prepareIncrementalPackage({oldDir:baseDir,newDir:appOutDir,fromVersion:baseVersion,toVersion:packageInfo.version,output:path.join(output,'incremental'),toolsDir:await ensureHdiffTools()});
    await customizeInstaller({output:path.dirname(installerInclude),templates:'D:/qx-contract-workbench-20261102/desktop/node_modules/app-builder-lib/templates/nsis',incremental,sevenZip:SEVEN_ZIP,sevenZipLicense});
    console.log('Changes-only installation package: '+JSON.stringify(incremental.stats));return false;
  },config:{
  appId:'cn.qunxing.harness.workbench',productName:'AI师兄法律助手平台',asar:true,compression:'normal',
  electronVersion:'44.8.0',electronDist:'D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist',
  directories:{output},files:['*.cjs','*.html','*.css','*.js','package.json','update-config.json'],
  publish:require('../desktop/update-config.json').feed,
  extraResources:[
    {from:thirdParty,to:'licenses/hdiffpatch'},
    {from:sevenZipLicense,to:'7zip-LICENSE.txt'},
    {from:path.join(stage,'workbench'),to:'workbench',filter:['**/*','!**/__pycache__/**','!**/*.pyc','!**/*.d.ts','!**/*.map','!bridge/test*.py','!bridge/check_*.py','!bridge/practice_eval_session.py','!plugins/**/*.test.mjs']},
    // electron-builder omits a FileSet's root node_modules unless copied explicitly.
    {from:path.join(stage,'workbench/node_modules'),to:'workbench/node_modules',filter:['**/*','!**/*.d.ts','!**/*.map']},
  ],
  afterPack:async context=>{
    appOutDir=context.appOutDir;
    // Differential NSIS packages use non-solid 7z archives for reusable blocks.
    const bundled=path.join(context.appOutDir,'resources/workbench');
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
  },
  win:{executableName:'QunxingWorkbench',target:[{target:'nsis',arch:['x64']}],signAndEditExecutable:false,artifactName:'Qunxing-Workbench-${version}-Setup.${ext}'},
  nsis:{oneClick:false,allowToChangeInstallationDirectory:true,allowElevation:false,perMachine:false,deleteAppDataOnUninstall:false,runAfterFinish:true,createDesktopShortcut:true,createStartMenuShortcut:true,include:installerInclude,differentialPackage:true,useZip:false},
  npmRebuild:false,
}}).then(paths=>{
  require('./update-release.cjs').signManifest(output,fs.readFileSync(path.join(__dirname,'update-notes.txt'),'utf8'));
  console.log(JSON.stringify(paths));
}).catch(error=>{console.error(error.message);process.exitCode=1});
