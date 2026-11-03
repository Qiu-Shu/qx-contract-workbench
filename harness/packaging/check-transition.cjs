// QA-only entry, excluded by the installer allowlist. Simulate provider acceptance,
// then exercise real encryption, IPC, background process and desktop transition.
const fs=require('node:fs');
const path=require('node:path');
require('electron').app.on('browser-window-created',(_event,window)=>window.webContents.setBackgroundThrottling(false));
require('../desktop/setup-service.cjs').validateKey=async()=>({ok:true,available:true});
const marker=path.join(process.env.QX_INSTALL_DATA,'test-open-settings');
setInterval(()=>{if(fs.existsSync(marker)&&global.qxOpenApiSettings){fs.unlinkSync(marker);global.qxOpenApiSettings()}},250);
require('../desktop/installed.cjs');
