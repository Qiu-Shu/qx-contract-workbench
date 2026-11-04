const path=require('node:path');
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const {build}=require('D:/qx-contract-workbench-20261102/desktop/node_modules/electron-builder');
const stage=path.resolve(process.argv[2]);
const output=path.resolve(process.argv[3]||path.join(stage,'dist'));
const shim=path.join(stage,'build-tools');fs.mkdirSync(shim,{recursive:true});
fs.writeFileSync(path.join(shim,'npm.cmd'),'@"C:\\Users\\Lenovo\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe" "D:\\qx-contract-workbench-20261102\\.local\\desktop-tools\\npm\\package\\bin\\npm-cli.js" %*\r\n');
process.env.PATH=shim+path.delimiter+path.dirname(process.execPath)+path.delimiter+process.env.PATH;
process.env.ELECTRON_BUILDER_COMPRESSION_LEVEL??='1';
const packageInfo=JSON.parse(fs.readFileSync(path.join(stage,'app/package.json'),'utf8'));
fs.writeFileSync(path.join(stage,'app/package-lock.json'),JSON.stringify({name:packageInfo.name,version:packageInfo.version,lockfileVersion:3,packages:{'':{name:packageInfo.name,version:packageInfo.version}}}));
build({publish:'never',projectDir:path.join(stage,'app'),...(process.argv[4]==='--prepackaged'?{prepackaged:path.join(output,'win-unpacked')}:{}),config:{
  appId:'cn.qunxing.harness.workbench',productName:'AI师兄法律助手平台',asar:true,compression:'normal',
  electronVersion:'44.8.0',electronDist:'D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist',
  directories:{output},files:['*.cjs','*.html','*.css','*.js','package.json','update-config.json'],
  publish:require('../desktop/update-config.json').feed,
  extraResources:[
    {from:path.join(stage,'workbench'),to:'workbench',filter:['**/*','!**/__pycache__/**','!**/*.pyc','!**/*.d.ts','!**/*.map','!bridge/test*.py','!bridge/check_*.py','!plugins/**/*.test.mjs']},
    // electron-builder omits a FileSet's root node_modules unless copied explicitly.
    {from:path.join(stage,'workbench/node_modules'),to:'workbench/node_modules',filter:['**/*','!**/*.d.ts','!**/*.map']},
  ],
  afterPack:async context=>{
    // Differential NSIS packages use non-solid 7z archives for reusable blocks.
    const bundled=path.join(context.appOutDir,'resources/workbench');
    for(const relative of ['node_modules/@deepseek-ai/dsh/lib/bin.js','node_modules/@deepseek-ai/libreoffice-kit-win32-x64/bin/libreoffice-kit.exe','node_modules/@deepseek-ai/libreoffice-kit-win32-x64/prebuilds.json','node_modules/@qunxing/desktop-session/attachment-preview.mjs','node_modules/@qunxing/desktop-session/client.js','browser/node_modules/bb-browser/dist/cli.js','runtime/python/python.exe','desktop-runner/installed-host.cjs','workspace-seed/AGENTS.md','config/templates/catalog.json','config/contract-0.2.0-defaults.json','plugins/privacy/client.js']){
      if(!fs.existsSync(path.join(bundled,relative)))throw Error('Required runtime file missing from package: '+relative);
    }
    const version=execFileSync(path.join(bundled,'runtime/node.exe'),[path.join(bundled,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'--version'],{cwd:bundled,windowsHide:true,timeout:30000,encoding:'utf8'}).trim();
    if(version!=='0.2.2-alpha.2')throw Error('Bundled Harness failed its startup check');
    execFileSync(path.join(bundled,'runtime/node.exe'),[path.resolve(__dirname,'../scripts/check_office_preview.mjs'),bundled],{windowsHide:true,timeout:30000,stdio:'pipe'});
    console.log('Packaged Node and Harness startup verified.');
  },
  win:{executableName:'QunxingWorkbench',target:[{target:'nsis',arch:['x64']}],signAndEditExecutable:false,artifactName:'Qunxing-Workbench-${version}-Setup.${ext}'},
  nsis:{oneClick:true,perMachine:false,deleteAppDataOnUninstall:false,runAfterFinish:true,createDesktopShortcut:true,createStartMenuShortcut:true,include:path.resolve(__dirname,'installer.nsh'),differentialPackage:true,useZip:false},
  npmRebuild:false,
}}).then(paths=>{
  require('./update-release.cjs').signManifest(output,fs.readFileSync(path.join(__dirname,'update-notes.txt'),'utf8'));
  console.log(JSON.stringify(paths));
}).catch(error=>{console.error(error.message);process.exitCode=1});
