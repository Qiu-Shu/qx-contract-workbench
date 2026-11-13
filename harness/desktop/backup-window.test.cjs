const {test}=require('node:test'),assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const path=require('node:path'),{pathToFileURL}=require('node:url');
function fixture(){
 const routes={},calls=[],windows=[];let busy=false,closed=0;
 class Window extends EventEmitter{
  constructor(options){super();this.options=options;windows.push(this);this.webContents=new EventEmitter();this.webContents.mainFrame={url:''};this.webContents.setWindowOpenHandler=fn=>{this.openHandler=fn;};}
  isDestroyed(){return false;}show(){calls.push('show');}focus(){calls.push('focus');}
  loadFile(file){this.webContents.mainFrame.url=pathToFileURL(file).href;return Promise.resolve();}
 }
 const controller={state:async()=>({selected:{}}),choose:async kind=>{calls.push(['choose',kind]);},act:async(action,input)=>{calls.push([action,input]);},isBusy:()=>busy};
 const view=require('./backup-window.cjs').createBackupWindow({app:{getPath:()=>path.resolve('synthetic-documents')},BrowserWindow:Window,
  ipcMain:{handle:(name,handler)=>{routes[name]=handler;}},dialog:{showOpenDialog:async(_win,options)=>{calls.push(['picker',options]);return {canceled:false,filePaths:[path.resolve('synthetic-picked')]};}},
  controller,onClosed:()=>closed++,canClose:()=>!busy});
 return {view,routes,calls,windows,setBusy:value=>{busy=value;},closed:()=>closed};
}
test('maintenance IPC accepts only its exact local main frame and rejects foreign senders and actions',async()=>{
 const f=fixture();f.view.show();const win=f.windows[0],event={sender:win.webContents,senderFrame:win.webContents.mainFrame};
 assert.deepEqual(Object.keys(f.routes).sort(),['qx:backup-action','qx:backup-choose','qx:backup-state']);
 assert.deepEqual(await f.routes['qx:backup-state'](event),{selected:{}});
 for(const foreign of [{sender:{},senderFrame:event.senderFrame},{sender:event.sender,senderFrame:{url:event.senderFrame.url}},
  {sender:event.sender,senderFrame:{url:'https://untrusted.invalid/'}}])assert.equal(await f.routes['qx:backup-state'](foreign),null);
 const before=f.calls.length;await f.routes['qx:backup-choose'](event,'executable');await f.routes['qx:backup-action'](event,'shell');assert.equal(f.calls.length,before);
 await f.routes['qx:backup-choose'](event,'reviewRoot');await f.routes['qx:backup-action'](event,'review',{});
 assert.ok(f.calls.some(call=>Array.isArray(call)&&call[0]==='review'));
});
test('maintenance window is isolated, opens without pausing, and its native picker selects directories only',async()=>{
 const f=fixture();f.view.show();const win=f.windows[0];
 assert.equal(win.options.webPreferences.sandbox,true);assert.equal(win.options.webPreferences.contextIsolation,true);assert.equal(win.options.webPreferences.nodeIntegration,false);
 assert.deepEqual(win.openHandler(),{action:'deny'});assert.equal(f.calls.some(call=>Array.isArray(call)&&call[0]==='pause'),false);
 const picked=await f.view.pick('backupParent');assert.equal(picked,path.resolve('synthetic-picked'));
 assert.deepEqual(f.calls.find(call=>Array.isArray(call)&&call[0]==='picker')[1].properties,['openDirectory']);
 assert.equal(await f.view.pick('execute'),null);
 let prevented=false;f.setBusy(true);win.emit('close',{preventDefault(){prevented=true;}});assert.equal(prevented,true);
 f.setBusy(false);prevented=false;win.emit('close',{preventDefault(){prevented=true;}});assert.equal(prevented,false);
 win.emit('closed');assert.equal(f.closed(),1);assert.equal(f.view.isOpen(),false);
});
