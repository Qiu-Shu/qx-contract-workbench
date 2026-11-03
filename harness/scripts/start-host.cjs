// Runs headlessly in Electron only to read the existing Windows-protected key.
// The key remains in memory and is passed solely to the local Harness process.
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {app,safeStorage} = require('electron');
const root = path.resolve(__dirname,'..');
const legacy = 'D:/qx-contract-workbench-20261102';
const dataParent = path.join(legacy,'.local/desktop-data');
const node = 'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe';
const {createModelCredentialStore} = require(path.join(legacy,'desktop/model-credentials.cjs'));
app.setName('qunxing-workbench-desktop');
app.setPath('userData',dataParent);
app.disableHardwareAcceleration();
app.whenReady().then(async()=>{
  const local=path.join(root,'.local'); fs.mkdirSync(local,{recursive:true});
  const profile=path.join(local,'dsh-home/profiles/web'); fs.mkdirSync(profile,{recursive:true});
  // UI settings are saved in this profile. Never overwrite them on each launch.
  const profilePatch=path.join(profile,'cordis.patch.yml');
  if(!fs.existsSync(profilePatch))fs.copyFileSync(path.join(root,'config/cordis.patch.yml'),profilePatch);
  const store=createModelCredentialStore({dataParent,safeStorage});
  let child;
  const status=await store.withSecret(secret=>{
    const log=fs.createWriteStream(path.join(local,'host.log'),{flags:'a'});
    child=spawn(node,[path.join(root,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'web','--no-open','--host','127.0.0.1','--port','3080'],{
      cwd:path.join(root,'workspace'), windowsHide:true,
      stdio:['ignore','pipe','pipe'], env:{...process.env,DSH_HOME:path.join(local,'dsh-home'),DEEPSEEK_API_KEY:secret,DSH_TELEMETRY_MODE:'OFF'}
    });
    let pending='';
    child.stdout.on('data',chunk=>{
      pending+=chunk.toString();
      let end;
      while((end=pending.indexOf('\n'))>=0){
        const line=pending.slice(0,end);pending=pending.slice(end+1);
        const match=line.match(/^dsh web: (http:\/\/127\.0\.0\.1:3080\/\?token=\S+)/);
        if(match){
          fs.writeFileSync(path.join(local,'runtime.json'),JSON.stringify({url:match[1],hostPid:child.pid,port:3080})+'\n');
          log.write('群兴本机服务已启动：http://127.0.0.1:3080\n');
        }else log.write(line+'\n');
      }
    });
    child.stderr.pipe(log,{end:false});
    child.on('error',()=>{console.error('本机服务未能启动，请查看 .local/host.log');app.exit(1);});
    child.on('close',code=>app.exit(code||0));
    fs.writeFileSync(path.join(local,'host-process.json'),JSON.stringify({launcherPid:process.pid,hostPid:child.pid,port:3080})+'\n');
  });
  if(status.status!=='saved'||!child){console.error('无法读取已有模型配置：'+(status.code||status.status));app.exit(1);}
}).catch(error=>{console.error('启动失败：'+error.message);app.exit(1);});
