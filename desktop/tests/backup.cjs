// Run after acceptance.cjs in the SAME synthetic output, so original file refs remain valid.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const repo=path.resolve(__dirname,'../..'),output=path.resolve(process.argv[2]);
const executable=process.argv[3]||path.join(repo,'desktop/node_modules/electron/dist/electron.exe');
const packaged=!!process.argv[3],data=path.join(output,'中文 用户资料'),archive=path.join(output,'合成 案件备份.qxbak');
const secret='synthetic-desktop-backup-only';
const report={packaged,checks:[],started:new Date().toISOString()};let app,page;
async function capture(name){const win=await app.browserWindow(page);const png=await win.evaluate(async w=>(await w.webContents.capturePage()).toPNG().toString('base64'));fs.writeFileSync(path.join(output,name),Buffer.from(png,'base64'));}
async function menu(label){await app.evaluate(({Menu},label)=>{const item=Menu.getApplicationMenu().items[0].submenu.items.find(x=>x.label===label);if(!item)throw Error('menu missing');item.click();},label);}
async function login(recovery=false){await page.waitForURL(/\/login$/,{timeout:60000});await page.locator('[name=username]').fill('桌面合成律师');await page.locator('[name=password]').fill('fiction123');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL(recovery?/\/recovery$/:/\/(workspace|assistant)$/);}
async function api(url,method='GET',body){return page.evaluate(async({url,method,body})=>{const csrf=document.cookie.split('; ').find(x=>x.startsWith('qx_csrf='))?.slice(8);const r=await fetch(url,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()};},{url,method,body});}
async function submit(operation,passphrase=secret){await page.locator('#backup-secret').fill(passphrase);if(operation==='backup')await page.locator('#backup-confirm').fill(passphrase);await page.locator('#maintenance-submit').click();}
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
(async()=>{try{
 assert.ok(fs.existsSync(path.join(data,'workspaces/main/workspace.json')));
 app=await _electron.launch({executablePath:executable,args:packaged?[]:[path.join(repo,'desktop')],cwd:repo,env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
 page=await app.firstWindow();await login();report.version=await app.evaluate(({app})=>app.getVersion());
 const matters=(await api('/api/matters')).data;assert.ok(matters.length);const matter=matters[0].id;
 const intake=await api('/api/intakes','POST',{request_id:crypto.randomUUID(),draft:{title:'备份合成接待',consultation:'备份前合成原话',client_reply:'合成客户回复',internal_notes:'合成内部记录'}});assert.equal(intake.status,201);
 const denied=await page.evaluate(()=>window.desktopSetup.maintenance({passphrase:'synthetic-denied'}));assert.equal(denied.ok,false);report.checks.push('business-page-cannot-maintain');
 await app.evaluate(({dialog},archive)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath:archive});dialog.showOpenDialog=async()=>({canceled:false,filePaths:[archive]});},archive);
 await menu('备份案件资料…');await page.locator('#maintenance').waitFor({state:'visible'});await capture('backup-form.png');
 await submit('backup');await page.locator('#maintenance-result').waitFor({state:'visible',timeout:120000});assert.ok(fs.statSync(archive).size>0);const initialHash=hash(archive);report.archiveSha256=initialHash;
 assert.equal(fs.readFileSync(archive).includes(Buffer.from(secret)),false);await capture('backup-created.png');report.checks.push('native-password-encrypted-verified-backup');
 await page.locator('#resume').click();await login();
 await menu('备份案件资料…');await page.locator('#maintenance').waitFor({state:'visible'});await submit('backup');await page.locator('#status').filter({hasText:'目标文件已存在'}).waitFor();assert.equal(hash(archive),initialHash);report.checks.push('existing-backup-not-overwritten');
 await menu('从备份建立核对副本…');await page.locator('#maintenance-title').filter({hasText:'从备份'}).waitFor();await submit('restore',secret+'wrong');await page.locator('#status').filter({hasText:'口令不正确'}).waitFor({timeout:60000});
 const restores=path.join(data,'workspaces/recovered');assert.deepEqual(fs.readdirSync(restores),[]);report.checks.push('wrong-password-no-published-copy');
 await submit('restore');await page.locator('#maintenance-result').waitFor({state:'visible',timeout:120000});await capture('restore-verified.png');
 const saved=JSON.parse(fs.readFileSync(path.join(data,'desktop-settings.json'),'utf8'));report.restoredWorkspace=saved.workspace;
 assert.match(saved.workspace,/^recovered\//);assert.equal(JSON.stringify(saved).includes(secret),false);
 await page.locator('#resume').click();await login(true);await capture('recovery-overview.png');
 assert.equal((await api('/api/intakes','POST',{})).status,409);assert.equal((await api('/api/matters','POST',{})).status,409);report.checks.push('restored-login-and-backend-readonly');
 await page.getByRole('link',{name:'备份合成接待',exact:true}).click();assert.match(await page.locator('body').innerText(),/备份前合成原话/);assert.match(await page.locator('body').innerText(),/合成内部记录/);await capture('recovery-intake.png');
 await page.goto(new URL('/recovery/matters/'+matter,page.url()).href);await capture('recovery-documents.png');
 const original=page.locator('a[href*="/originals/"]').first(),artifact=page.locator('a[href*="/artifacts/"]').first();assert.equal(await original.count(),1);assert.equal(await artifact.count(),1);
 for(const [name,link] of [['original',original],['historical',artifact]]){
   const target=path.join(output,'restored-'+name+'.docx');const done=app.evaluate(({BrowserWindow},target)=>new Promise(resolve=>{BrowserWindow.getAllWindows()[0].webContents.session.once('will-download',(_e,item)=>{item.setSavePath(target);item.once('done',(_e,state)=>resolve(state));});}),target);
   await link.click();assert.equal(await done,'completed');assert.equal(fs.readFileSync(target).subarray(0,2).toString(),'PK');report[name+'Sha256']=hash(target);
 }
 const prior=JSON.parse(fs.readFileSync(path.join(output,'report.json'),'utf8'));assert.equal(report.historicalSha256,prior.export.sha256);report.checks.push('historical-word-byte-equality','original-download','intake-history-readable');
 const win=await app.browserWindow(page);await win.evaluate(w=>{w.setSize(760,760);w.webContents.setZoomFactor(1.5);});await capture('recovery-small.png');const dims=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(dims.scroll<=dims.width+1);report.checks.push('small-window-reading');
 await menu('返回原工作区');await login();assert.ok((await api('/api/matters')).data.some(x=>x.id===matter));assert.equal((await api('/api/intakes/'+intake.data.id)).status,200);report.checks.push('return-original-workspace');
 await app.close();app=null;report.status='PASS';
 }catch(error){report.status='FAIL';report.error=error.stack;if(page&&!page.isClosed())await capture('backup-failure.png').catch(()=>{});throw error;}
 finally{if(app)await app.close();report.finished=new Date().toISOString();fs.writeFileSync(path.join(output,'backup-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})().catch(error=>{console.error(error);process.exitCode=1;});
