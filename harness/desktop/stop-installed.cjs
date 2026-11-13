const path=require('node:path');
const {stopInstalledHost}=require('./installed-stop.cjs');
const anchor=process.env.QX_INSTALL_DATA||path.join(process.env.APPDATA,'QunxingHarness');
Promise.resolve().then(()=>{
  const {data}=require('./data-location.cjs').resolveDataLocation(anchor);
  return stopInstalledHost(data);
}).catch(()=>{console.error('工作台后台未退出或资料目录需修复，请打开备份与恢复检查后重试。');process.exitCode=1});
