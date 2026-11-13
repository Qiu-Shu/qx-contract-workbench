const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
test('busy main windows reject user close but allow resume to replace the previous window',async()=>{
 const windows=[],seen={backup:0,shown:0};let busy=false,maintenance=false;
 class Window extends EventEmitter{
  constructor(){super();windows.push(this);this.destroyed=false;this.webContents=new EventEmitter();
   Object.assign(this.webContents,{session:{setPermissionCheckHandler(){},setPermissionRequestHandler(){}},setWindowOpenHandler(){},getURL:()=>this.url,executeJavaScript:async()=>false});}
  isDestroyed(){return this.destroyed;}show(){seen.shown++;}focus(){}setTitle(){}
  loadURL(url){this.url=url;return Promise.resolve();}loadFile(file){this.url=require('node:url').pathToFileURL(file).href;return Promise.resolve();}
  close(){let stopped=false;this.emit('close',{preventDefault(){stopped=true;}});if(!stopped){this.destroyed=true;this.emit('closed');}}
 }
 const app=new EventEmitter();Object.assign(app,{setName(){},setPath(){},requestSingleInstanceLock:()=>true,whenReady:()=>Promise.resolve(),quit(){}});
 const context={__dirname,process:{env:{QX_WORKBENCH_ROOT:path.resolve('synthetic-main'),QX_HARNESS_URL:'http://127.0.0.1:54321/'},argv:[]},URL,console,
  qxBackupBusy:()=>busy,qxIsMaintenance:()=>maintenance,qxOpenBackup:()=>seen.backup++};context.global=context;
 context.require=name=>{
  if(name==='electron')return {app,BrowserWindow:Window,Menu:{buildFromTemplate:items=>items,setApplicationMenu:items=>{seen.menu=items;}},ipcMain:{handle(){},on(){}},dialog:{},shell:{},net:{}};
  if(name==='node:fs')return {mkdirSync(){},readFileSync(){throw Error('unused synthetic read');}};
  return require(name);
 };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'main.cjs'),'utf8'),context);await context.qxMainReady;
 assert.equal(windows.length,1);busy=true;windows[0].close();assert.equal(windows[0].destroyed,false);
 await context.qxReloadMain();assert.equal(windows.length,2);assert.equal(windows[0].destroyed,true);assert.equal(windows[1].destroyed,false);
 const menu=seen.menu[0].submenu;assert.ok(menu.find(item=>item.label==='备份与恢复'));
 maintenance=true;menu.find(item=>item.label==='手机微信').click();assert.equal(seen.backup,1);
 const before=seen.shown;windows[1].emit('ready-to-show');assert.equal(seen.shown,before);
 await context.qxReloadMain();assert.equal(windows.length,2);
});
