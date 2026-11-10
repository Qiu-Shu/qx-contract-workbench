const path=require('node:path');
const {stopInstalledHost}=require('./installed-stop.cjs');
const data=process.env.QX_INSTALL_DATA||path.join(process.env.APPDATA,'QunxingHarness');
stopInstalledHost(data).catch(()=>{console.error('工作台后台未退出，请关闭工作台后重试。');process.exitCode=1});
