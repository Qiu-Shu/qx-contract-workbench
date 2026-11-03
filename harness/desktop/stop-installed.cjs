const fs=require('node:fs');
const path=require('node:path');
const {stopRuntime}=require('./installed-runtime.cjs');
const data=process.env.QX_INSTALL_DATA||path.join(process.env.APPDATA,'QunxingHarness');
(async()=>{
  let runtime;try{runtime=JSON.parse(fs.readFileSync(path.join(data,'.local/runtime.json'),'utf8'))}catch{return}
  try{process.kill(runtime.launcherPid,0)}catch{return}
  await stopRuntime(runtime);
})().catch(()=>{console.error('工作台后台未退出，请关闭工作台后重试。');process.exitCode=1});
