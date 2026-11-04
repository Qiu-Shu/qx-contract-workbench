// Real hidden Electron shell, synthetic local pages; no credentials or model calls.
const {app,BrowserWindow}=require('electron');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'.local/white-screen-20261104');
fs.mkdirSync(out,{recursive:true});
process.env.QX_WORKBENCH_ROOT=root;
process.env.QX_DESKTOP_DATA=path.join(out,'synthetic-shell-profile');
process.env.QX_DESKTOP_HIDDEN='1';
app.setPath('userData',process.env.QX_DESKTOP_DATA);
const events=[],checks=[];
global.qxDesktopLog=(event,fields)=>events.push({event,...fields});
const server=http.createServer((_req,res)=>{
 res.writeHead(200,{'content-type':'text/html; charset=utf-8'});
 res.end('<!doctype html><html><body><div id="root"></div><script>throw new TypeError("SYNTHETIC_PRIVATE_DO_NOT_LOG")</script></body></html>');
});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function inspect(wc){return wc.executeJavaScript(`(()=>{const n=document.querySelector('#qx-connection-notice');return {hidden:n?.hidden,text:n?.shadowRoot?.textContent||'',draft:document.querySelector('textarea')?.value}})()`)}
server.listen(0,'127.0.0.1',async()=>{
 try{
  process.env.QX_HARNESS_URL='http://127.0.0.1:'+server.address().port+'/?token=synthetic-test';
  require('./main.cjs');await global.qxMainReady;
  const win=BrowserWindow.getAllWindows()[0];
  await delay(700);assert.match((await inspect(win.webContents)).text,/正在打开工作台/);
  await delay(16000);assert.match((await inspect(win.webContents)).text,/界面尚未加载完成/);
  assert(events.some(e=>e.phase==='load-timeout'));checks.push('real shell catches empty-root script failure and timeout');
  assert(events.some(e=>e.event==='page_script_error'&&e.errorName==='TypeError'));
  checks.push('isolated-world boundary still records main-page JavaScript errors');
  await win.webContents.executeJavaScript(`document.getElementById('root').innerHTML='<h1>合成测试</h1><textarea>合成草稿</textarea>'`);
  await delay(700);assert.equal((await inspect(win.webContents)).hidden,true);
  assert(events.some(e=>e.phase==='page-ready'));checks.push('late render clears notice and logs readiness');
  await win.webContents.executeJavaScript(`document.getElementById('root').replaceChildren()`);
  await delay(700);assert.match((await inspect(win.webContents)).text,/界面显示中断/);
  checks.push('later empty renderer recovers without reloading or submitting');
  assert(!JSON.stringify(events).includes('SYNTHETIC_PRIVATE'));
  assert(!JSON.stringify(events).includes('token='));checks.push('logs exclude content and credential URL');
  fs.writeFileSync(path.join(out,'synthetic-electron.png'),(await win.webContents.capturePage()).toPNG());
  fs.writeFileSync(path.join(out,'synthetic-electron-result.json'),JSON.stringify({passed:true,checks,events},null,2));
  console.log(JSON.stringify({passed:true,checks,events}));
  server.close();app.quit();
 }catch(error){fs.writeFileSync(path.join(out,'synthetic-electron-result.json'),JSON.stringify({passed:false,checks,error:String(error),events},null,2));server.close();app.exit(1);}
});
setTimeout(()=>app.exit(2),45000).unref();
