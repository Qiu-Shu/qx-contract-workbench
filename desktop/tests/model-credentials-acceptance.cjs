// Test-only observation/control around the actual main. Never shipped in build.files.
const fs=require('node:fs'),path=require('node:path');
const {app,BrowserWindow,Menu}=require('electron');
const project=path.resolve(__dirname,'../..'),evidence=process.env.QX_PROBE_EVIDENCE;
const report={electron:process.versions.electron,events:[],backend_configs:[],windows:[]};
const output=path.join(evidence,'bootstrap.json');
const save=()=>fs.writeFileSync(output,JSON.stringify(report,null,2));
let primary,timer,handling=false,observedBackend;
const backendPath=path.join(project,'desktop/backend.cjs');
const {Backend}=require(backendPath);
class ObservedBackend extends Backend {
  constructor(executable,args){
    const entry=process.env.QX_PROBE_SETTINGS_ENTRY;
    const frozen=process.env.QX_PROBE_FROZEN_BACKEND;
    super(frozen||executable,frozen?[]:entry?['-X','utf8',entry]:args);
    observedBackend=this;
  }
  async start(config){
    report.backend_configs.push({keys:Object.keys(config).sort(),contains_model_credential:JSON.stringify(config).includes('synthetic-native-secret-')});save();
    const ready=await super.start(config);report.ready={port:ready.port,pid:this.child.pid};save();
    this.child.once('close',(code,signal)=>{report.backend_exit={code,signal};save();});return ready;
  }
  async configureModel(payload){
    const result=await super.configureModel(payload);
    (report.model_controls ||= []).push({operation:'configure',ok:result.ok,status:result.status,model:payload.config.model});save();return result;
  }
  async disableModel(){
    const result=await super.disableModel();
    (report.model_controls ||= []).push({operation:'disable',ok:result.ok,status:result.status});save();return result;
  }
}
require.cache[require.resolve(backendPath)].exports={Backend:ObservedBackend};
app.on('browser-window-created',(_event,win)=>{
  if(!primary)primary=win;
  if(win===primary)win.webContents.on('did-finish-load',()=>{report.page_loads=(report.page_loads||0)+1;report.page_url=win.webContents.getURL();save();});
  const pref=win.webContents.getLastWebPreferences();
  report.windows.push({nodeIntegration:pref.nodeIntegration,contextIsolation:pref.contextIsolation,sandbox:pref.sandbox,webSecurity:pref.webSecurity});save();
});
app.on('will-quit',()=>{clearInterval(timer);report.events.push('actual_will_quit');save();});
require(path.join(project,'desktop/main.cjs'));
app.whenReady().then(()=>{
  timer=setInterval(async()=>{
    const commandPath=path.join(evidence,'command.json');
    if(handling||!fs.existsSync(commandPath))return;
    handling=true;
    let request;
    try{
      request=JSON.parse(fs.readFileSync(commandPath,'utf8'));fs.unlinkSync(commandPath);
      let value;
      if(request.action==='menu'){
        const item=Menu.getApplicationMenu().items[0].submenu.items.find(i=>i.label===request.label);
        if(!item)throw Error('MENU_NOT_FOUND');await item.click();value={clicked:true};
      }else if(request.action==='window'){
        primary.setSize(request.width,request.height);primary.webContents.setZoomFactor(request.zoom);value={changed:true,...primary.getContentBounds(),zoom:primary.webContents.getZoomFactor()};
      }else if(request.action==='capture'){
        if(!/^[a-z0-9-]+\.png$/.test(request.name))throw Error('TEST_CAPTURE_NAME');
        const capture=await primary.webContents.capturePage();fs.writeFileSync(path.join(evidence,'..',request.name),capture.toPNG());value=capture.getSize();
      }else if(request.action==='stop-backend'){
        observedBackend.child.kill();value={stopped:true};
      }else if(request.action==='crash-renderer'){
        value={requested:true,loads:report.page_loads||0};primary.webContents.forcefullyCrashRenderer();
      }else if(request.action==='other-window'){
        const other=new BrowserWindow({show:false,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true,preload:path.join(project,'desktop/preload.cjs')}});
        try{
          await other.loadFile(path.join(project,'desktop/setup.html'));
          value=await other.webContents.executeJavaScript(`(async()=>({status:await desktopSetup.modelStatus(),save:await desktopSetup.modelSave('synthetic-native-secret-untrusted-window'),remove:await desktopSetup.modelRemove(),runtime:await desktopSetup.modelRuntimeStatus(),configure:await desktopSetup.modelConfigure('deepseek-flash'),disable:await desktopSetup.modelDisable(),node:typeof require}))()`);
        }finally{other.destroy();}
      }else throw Error('UNKNOWN_TEST_COMMAND');
      fs.writeFileSync(path.join(evidence,'response.json'),JSON.stringify({id:request.id,value}));
    }catch(error){
      fs.writeFileSync(path.join(evidence,'response.json'),JSON.stringify({id:request?.id,error:'TEST_CONTROL_FAILED'}));
    }finally{handling=false;}
  },40);
});
