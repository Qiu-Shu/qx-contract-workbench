// Actual development Electron window and its owned Python backend. Synthetic only.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),assert=require('node:assert/strict');
const repo=path.resolve(__dirname,'../..'),output=path.resolve(process.argv[2]);
const data=path.join(output,'中文 附件用户资料'),source=path.join(output,'合成 附件.docx');
const executable=path.join(repo,'desktop/node_modules/electron/dist/electron.exe');
const quote='独立虚构咨询：客户自述付款 35000 元；<原话 & 待核验>。';
const report={scope:'development Electron shell with owned source Python backend; not frozen backend or installer',
  checks:[],processes:[],viewports:[],started:new Date().toISOString(),dataParent:data};
const errors=[],external=[],modelSubmissions=[];
let app,page,conversation;
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
async function launch(){
  app=await _electron.launch({executablePath:executable,args:[path.join(repo,'desktop')],cwd:repo,
    env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
  report.processes.push({electronPid:app.process().pid});
  page=await app.firstWindow();
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{
    const url=new URL(request.url());
    if(/^https?:$/.test(url.protocol)&&url.hostname!=='127.0.0.1')external.push(url.origin);
    if(request.method()==='POST'&&url.pathname.endsWith('/messages'))modelSubmissions.push(url.pathname);
  });
}
async function close(){
  if(!app)return;
  const process=app.process(),origin=/^http/.test(page.url())?new URL(page.url()).origin:null;
  await app.close();app=null;
  const entry=report.processes.at(-1);entry.exitCode=process.exitCode;entry.signalCode=process.signalCode;
  if(origin){await assert.rejects(fetch(origin+'/login'));entry.ownedBackendPortClosed=true;}
}
async function login(){
  await page.waitForURL(/\/login$/,{timeout:60000});
  await page.locator('[name=username]').fill('桌面附件合成律师');
  await page.locator('[name=password]').fill('fiction123');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.waitForURL(/\/assistant$/);await page.locator('#composer').waitFor();
}
async function capture(name){
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const win=await app.browserWindow(page);
  const png=await win.evaluate(async value=>(await value.webContents.capturePage()).toPNG().toString('base64'));
  fs.writeFileSync(path.join(output,name),Buffer.from(png,'base64'));
}
async function read(url){return page.evaluate(async path=>{const response=await fetch(path);if(!response.ok)throw Error('HTTP '+response.status);return response.json();},url);}
async function saved(){await page.waitForFunction(()=>document.querySelector('#save-status').textContent==='草稿已保存到本机');}
async function preview(){
  await page.locator('#material-list').getByRole('button',{name:'核对原文',exact:true}).click();
  await page.locator('#material-preview-content').getByText(quote,{exact:true}).waitFor();
}
(async()=>{try{
  assert.equal(fs.existsSync(path.join(data,'workspaces/main')),false,'Use a new isolated output directory.');
  fs.mkdirSync(output,{recursive:true});
  const generated=spawnSync(path.join(repo,'.venv/Scripts/python.exe'),['-c',
    'from docx import Document; import sys; d=Document(); d.add_paragraph(sys.argv[2]); d.save(sys.argv[1])',source,quote],
    {cwd:repo,encoding:'utf8',windowsHide:true});
  assert.equal(generated.status,0,generated.stderr);report.originalSha256=hash(source);
  await launch();await page.locator('#setup').waitFor({state:'visible',timeout:45000});
  await page.locator('#username').fill('桌面附件合成律师');await page.locator('#password').fill('fiction123');
  await page.locator('#confirm').fill('fiction123');await page.locator('#setup button[type=submit]').click();
  await login();assert.equal(await page.evaluate(()=>typeof require),'undefined');
  assert.equal(await page.evaluate(()=>window.desktopSetup.state()),null);
  assert.equal(await page.locator('#send').isDisabled(),true);
  report.checks.push('native_setup_login_home_isolation_and_generation_disabled');
  assert.equal((await read('/api/assistant/conversations')).items.length,0);
  await page.locator('#add-material').click();await page.locator('#material-file').setInputFiles(source);
  assert.equal(await page.locator('#upload-material').isDisabled(),true);
  assert.equal((await read('/api/assistant/conversations')).items.length,0);
  await capture('attachments-selected-before-consent.png');
  await page.locator('#material-consent').check();await page.locator('#upload-material').click();
  await page.locator('#material-list').getByText(path.basename(source),{exact:true}).waitFor();await saved();
  conversation=page.url().split('/').pop();assert.match(conversation,/^[a-f0-9-]{36}$/);
  const base='/api/assistant/conversations/'+conversation;
  let materials=await read(base+'/materials');assert.equal(materials.attachments.length,1);
  assert.equal(materials.attachments[0].sha256,report.originalSha256);
  assert.equal((await read('/api/matters')).length,0);assert.equal((await read('/api/intakes')).items.length,0);
  assert.equal((await read(base)).messages.length,0);
  report.attachmentId=materials.attachments[0].id;report.conversationId=conversation;
  report.checks.push('window_file_selection_consent_attachment_only_creation_no_hidden_case');
  await page.locator('#material-list').getByRole('button',{name:'核对原文',exact:true}).click();
  await page.getByRole('button',{name:'读取 DOCX',exact:true}).click();
  await page.locator('#material-preview-content').getByText(quote,{exact:true}).waitFor();await saved();
  assert.match(await page.locator('#material-preview-content').innerText(),/读取版本 1/);
  assert.match(await page.locator('#material-preview-content').innerText(),/待核实/);
  assert.equal(await page.locator('#material-preview-content script').count(),0);
  await capture('attachments-source.png');
  report.checks.push('window_docx_parse_source_quote_reading_revision_and_unverified_state');
  const downloaded=path.join(output,'下载的合成原件.docx');
  const downloading=app.evaluate(({BrowserWindow},target)=>new Promise(resolve=>{
    BrowserWindow.getAllWindows()[0].webContents.session.once('will-download',(_event,item)=>{
      item.setSavePath(target);item.once('done',(_event,state)=>resolve(state));
    });
  }),downloaded);
  await page.getByRole('link',{name:'下载受保护原件',exact:true}).click();
  assert.equal(await downloading,'completed');assert.equal(hash(downloaded),report.originalSha256);
  report.checks.push('authenticated_original_download_byte_equality');
  await page.locator('#close-material-preview').click();
  const draft='独立合成咨询草稿，附件原文尚未核验。';await page.locator('#composer').fill(draft);await saved();
  await page.reload();await saved();assert.equal(await page.locator('#composer').inputValue(),draft);
  await preview();await capture('attachments-reloaded.png');
  report.checks.push('page_reload_retains_draft_attachment_selection_and_exact_source');
  const win=await app.browserWindow(page);
  for(const factor of [1,1.25,1.5]){
    await win.evaluate((window,value)=>{window.setSize(760,760);window.webContents.setZoomFactor(value);},factor);
    await page.locator('#material-preview-title').scrollIntoViewIfNeeded();
    const size=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,height:innerHeight}));
    assert.ok(size.scroll<=size.width+1,JSON.stringify(size));report.viewports.push({factor,...size});
    await capture('attachments-window-'+factor+'.png');
  }
  await win.evaluate(window=>{window.setSize(1366,900);window.webContents.setZoomFactor(1);});
  report.checks.push('actual_narrow_window_and_display_zoom_keep_source_readable');
  await page.locator('#close-material-preview').click();await page.locator('#new-conversation').click();
  assert.equal(await page.locator('#material-list').innerText(),'');
  assert.equal(await page.locator('#material-section').isVisible(),false);
  assert.equal(await page.locator('#material-preview').isVisible(),false);
  await page.locator('#conversation-list [data-conversation-id="'+conversation+'"]').click();await saved();await preview();
  report.checks.push('new_conversation_clears_materials_then_explicit_reopen_restores_scope');
  await close();await launch();await login();
  await page.locator('#conversation-list [data-conversation-id="'+conversation+'"]').click();await saved();
  assert.equal(await page.locator('#composer').inputValue(),draft);await preview();
  await capture('attachments-restarted.png');assert.equal(hash(source),report.originalSha256);
  materials=await read(base+'/materials');assert.equal(materials.items[0].parse_revision,1);
  report.checks.push('owned_process_shutdown_and_actual_electron_restart_preserve_materials');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.deepEqual(modelSubmissions,[]);
  report.checks.push('no_script_errors_external_requests_or_model_submissions');
  report.status='PASS';
}catch(error){report.status='FAIL';report.error=error.stack;if(page&&!page.isClosed())await capture('attachments-failure.png').catch(()=>{});throw error;}
finally{if(app)await close();report.finished=new Date().toISOString();report.count=report.checks.length;
  fs.writeFileSync(path.join(output,'attachments-electron-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})().catch(error=>{console.error(error);process.exitCode=1;});
