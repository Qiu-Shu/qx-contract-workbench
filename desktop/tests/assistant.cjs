// Run after acceptance.cjs in the same isolated synthetic output.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const repo=path.resolve(__dirname,'../..'),output=path.resolve(process.argv[2]);
const executable=process.argv[3]||path.join(repo,'desktop/node_modules/electron/dist/electron.exe');
const packaged=!!process.argv[3],data=path.join(output,'中文 用户资料');
const launch=()=>_electron.launch({executablePath:executable,args:packaged?[]:[path.join(repo,'desktop')],cwd:repo,
  env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
const report={packaged,checks:[],viewports:[],started:new Date().toISOString()};
let app,page;
const errors=[],external=[],submissions=[];
async function login(){
  page=await app.firstWindow();
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{
    const url=new URL(request.url());
    if(/^https?:$/.test(url.protocol)&&url.hostname!=='127.0.0.1')external.push(url.origin);
    if(request.method()==='POST'&&url.pathname.endsWith('/messages'))submissions.push(url.pathname);
  });
  await page.waitForURL(/\/login$/,{timeout:60000});
  await page.locator('[name=username]').fill('桌面合成律师');
  await page.locator('[name=password]').fill('fiction123');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.waitForURL(/\/assistant$/);
  await page.locator('#composer').waitFor();
}
async function saved(){await page.waitForFunction(()=>document.querySelector('#save-status').textContent==='草稿已保存到本机');}
async function read(url){return page.evaluate(async url=>{const r=await fetch(url);if(!r.ok)throw Error('HTTP '+r.status);return r.json();},url);}
async function capture(name){const win=await app.browserWindow(page);const png=await win.evaluate(async w=>(await w.webContents.capturePage()).toPNG().toString('base64'));fs.writeFileSync(path.join(output,name),Buffer.from(png,'base64'));}
(async()=>{try{
  assert.ok(fs.existsSync(path.join(data,'workspaces/main/workspace.json')));
  app=await launch();await login();
  assert.equal(await page.evaluate(()=>typeof require),'undefined');
  assert.equal(await page.evaluate(()=>window.desktopSetup.state()),null);
  assert.equal(await page.locator('#send').isDisabled(),true);
  assert.equal(await page.locator('#add-material').isDisabled(),false);
  report.checks.push('native-default-home-isolated-no-node-empty-composer-and-material-entry');
  await capture('assistant-empty.png');
  const text='独立合成咨询：甲称已支付35000元；尚未核实。\n请保留原话与待核状态。';
  await page.locator('#composer').fill(text);await saved();
  const id=page.url().split('/').pop();assert.match(id,/^[a-f0-9-]{36}$/);
  await page.locator('#skill-cards [data-skill=client_reply]').click();
  assert.equal(await page.locator('#composer').inputValue(),text);
  await page.locator('#composer').press('Shift+Enter');await saved();
  const persisted=await page.locator('#composer').inputValue();assert.equal(persisted,text+'\n');
  assert.equal(await page.locator('#composer').inputValue(),persisted);
  report.checks.push('autosave-skill-preserves-text-and-shift-enter-newline');
  const win=await app.browserWindow(page);
  for(const factor of [1,1.25,1.5]){
    await win.evaluate((w,f)=>{w.setSize(760,760);w.webContents.setZoomFactor(f);},factor);
    await page.locator('#composer').scrollIntoViewIfNeeded();
    const size=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
    assert.ok(size.scroll<=size.width+1);report.viewports.push({factor,...size});
    await capture('assistant-window-'+factor+'.png');
  }
  await page.locator('#nav-toggle').click();
  await page.locator('#sidebar [data-skill=material_organize]').click();
  assert.equal(await page.locator('#nav-toggle').getAttribute('aria-expanded'),'false');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'composer');
  report.checks.push('actual-window-zoom-layout-and-menu-focus');
  await win.evaluate(w=>{w.setSize(1366,900);w.webContents.setZoomFactor(1);});
  await page.reload();await saved();
  assert.equal(await page.locator('#composer').inputValue(),persisted);
  assert.equal((await read('/api/assistant/conversations/'+id)).messages.length,0);
  await capture('assistant-draft.png');
  report.checks.push('reload-retrieves-draft-without-message');
  const origin=new URL(page.url()).origin;
  await app.close();app=null;await assert.rejects(fetch(origin+'/login'));
  app=await launch();await login();
  await page.locator('#conversation-list [data-conversation-id="'+id+'"]').click();
  await saved();assert.equal(await page.locator('#composer').inputValue(),persisted);
  report.checks.push('owned-server-stops-and-app-restart-keeps-draft');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.deepEqual(submissions,[]);
  report.checks.push('no-script-errors-external-requests-or-generation-submissions');
  report.status='PASS';
}catch(error){report.status='FAIL';report.error=error.stack;if(page&&!page.isClosed())await capture('assistant-failure.png').catch(()=>{});throw error;}
finally{if(app)await app.close();report.finished=new Date().toISOString();fs.writeFileSync(path.join(output,'assistant-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})().catch(error=>{console.error(error);process.exitCode=1;});
