// Test-only instrumentation: require the real main and keep its BrowserWindow policy.
const fs=require('node:fs');
const path=require('node:path');
const {app}=require('electron');
const project=path.resolve(__dirname,'../..');
const mode=process.env.QX_PROBE_MODE || 'default';
const evidence=path.resolve(process.env.QX_PROBE_EVIDENCE);
const report={mode,events:[],electron:process.versions.electron,project};
function save(){fs.writeFileSync(path.join(evidence,'bootstrap.json'),JSON.stringify(report,null,2));}
const backendPath=path.join(project,'desktop/backend.cjs');
const {Backend}=require(backendPath);
class ObservedBackend extends Backend {
  constructor(executable,args) {
    if(mode==='synthetic')args=[path.join(__dirname,'electron_synthetic_entry.py')];
    if(mode==='frozen'){executable=process.env.QX_PROBE_FROZEN_EXE;args=[];}
    super(executable,args);report.backend={executable,args};save();
  }
  async start(config) {
    const ready=await super.start(config);
    report.ready={port:ready.port,pid:this.child.pid};report.events.push('actual_backend_ready');save();
    this.child.once('close',(code,signal)=>{report.backend_exit={code,signal};save();});
    return ready;
  }
}
require.cache[require.resolve(backendPath)].exports={Backend:ObservedBackend};
app.on('browser-window-created',(_event,window)=>{
  report.events.push('actual_main_browser_window_created');
  const prefs=window.webContents.getLastWebPreferences();
  report.window={nodeIntegration:prefs.nodeIntegration,contextIsolation:prefs.contextIsolation,
    sandbox:prefs.sandbox,webSecurity:prefs.webSecurity};
  report.preference_keys=Object.keys(prefs);save();
  window.webContents.on('did-finish-load',()=>{report.last_url=window.webContents.getURL();save();});
});
app.on('will-quit',()=>{report.events.push('actual_app_will_quit');save();});
require(path.join(project,'desktop/main.cjs'));
