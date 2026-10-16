// Real Electron UI in a synthetic workspace, optionally copied from 0.2.0.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const repo=path.resolve(__dirname,'../..'),output=path.resolve(process.argv[2]);
const executable=process.argv[3]||path.join(repo,'desktop/node_modules/electron/dist/electron.exe');
const packaged=!!process.argv[3], data=path.join(output,'中文 用户资料');
fs.mkdirSync(output,{recursive:true});
const launch=()=>_electron.launch({executablePath:executable,args:packaged?[]:[path.join(repo,'desktop')],cwd:repo,
 env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
const report={packaged,checks:[],started:new Date().toISOString()};let app,page;
async function capture(name){await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));const win=await app.browserWindow(page);const png=await win.evaluate(async w=>(await w.webContents.capturePage()).toPNG().toString('base64'));fs.writeFileSync(path.join(output,name),Buffer.from(png,'base64'));}
async function login(){await page.waitForURL(/\/login$/,{timeout:60000});await page.locator('[name=username]').fill('桌面合成律师');await page.locator('[name=password]').fill('fiction123');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL(/\/workspace$/);await page.locator('#list-scope').filter({hasText:'已加载'}).waitFor();}
async function create(title,original){await page.locator('#open-create').click();await page.locator('#create-intake [name=title]').fill(title);await page.locator('#create-intake [name=consultation]').fill(original);await page.locator('#create-intake button').click();await page.waitForURL(/\/intakes\/[a-f0-9-]+$/);await page.waitForFunction(()=>document.querySelector('#save-state').innerText.includes('已保存'));return page.url().split('/').pop();}
async function api(url){return page.evaluate(async url=>{const r=await fetch(url);return {status:r.status,data:await r.json()};},url);}
async function download(audience){const target=path.join(output,audience+'.docx');const saved=app.evaluate(({BrowserWindow},target)=>new Promise(resolve=>{BrowserWindow.getAllWindows()[0].webContents.session.once('will-download',(_e,item)=>{item.setSavePath(target);item.once('done',(_e,state)=>resolve(state));});}),target);await page.locator('#export-'+audience).click();assert.equal(await saved,'completed');assert.equal(fs.readFileSync(target).subarray(0,2).toString(),'PK');}
(async()=>{try{
 const existed=fs.existsSync(path.join(data,'workspaces/main/workspace.json'));
 app=await launch();page=await app.firstWindow();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 if(!existed){await page.locator('#setup').waitFor({state:'visible'});await page.locator('#username').fill('桌面合成律师');await page.locator('#password').fill('fiction123');await page.locator('#confirm').fill('fiction123');await page.locator('#setup button[type=submit]').click();}
 await login();report.version=await app.evaluate(({app})=>app.getVersion());
 assert.equal(await page.evaluate(()=>navigator.clipboard.readText().then(()=>false,()=>true)),true);
 report.checks.push('clipboard-read-remains-denied');
 const oldMatters=(await api('/api/matters')).data;report.oldMatterIds=oldMatters.map(x=>x.id);
 if(existed){assert.ok(oldMatters.length>0);assert.ok(fs.existsSync(path.join(data,'workspaces/main/upgrade-intake-v1.json')));report.checks.push('legacy-upgrade-login-and-cases');}
 await capture('workspace.png');
 const a=await create('合成接待甲：买卖货款','甲原话：对方交货后尚有货款未付，细节待核。');report.intakeId=a;
 await page.locator('[name=contact]').fill('合成联系人 INTERNAL_CONTACT');
 await page.locator('[name=questions]').fill('付款时间如何约定？\n是否有签收凭证？');
 await page.locator('#add-material').click();await page.locator('#materials input').fill('交货与付款约定');
 await page.locator('#materials select').selectOption('received');
 await page.locator('[name=follow_up_at]').fill('2026-10-20T10:30');
 await page.locator('[name=follow_up_note]').fill('下次跟进补充签收凭证');
 await page.locator('[name=client_reply]').fill('请补充交货与付款约定，我们核对后继续沟通。');
 await page.locator('[name=internal_notes]').fill('INTERNAL_ONLY：尚需核对主体与期间，不构成结论。');
 assert.equal(await page.locator('#export-internal').isDisabled(),true);
 await page.locator('#save-intake').click();await page.waitForFunction(()=>document.querySelector('#save-state').innerText==='第 2 版已保存');
 report.checks.push('ui-register-followup-materials-and-version','unsaved-export-disabled');
 await page.locator('#copy-client').click();await page.waitForFunction(()=>document.querySelector('#message').innerText.includes('已复制客户回复'));
 assert.equal(await app.evaluate(({clipboard})=>clipboard.readText()),'请补充交货与付款约定，我们核对后继续沟通。');
 await page.locator('#copy-internal').click();await page.waitForFunction(()=>document.querySelector('#message').innerText.includes('已复制律师内部意见'));
 assert.match(await app.evaluate(({clipboard})=>clipboard.readText()),/^INTERNAL_ONLY/);report.checks.push('separate-client-internal-clipboard');
 await page.locator('#client-checked').check();await download('client');await download('internal');report.checks.push('actual-electron-two-word-downloads');
 assert.match(await page.locator('#history-content').textContent(),/交货与付款约定（已收到待核）/);
 assert.match(await page.locator('#history-content').textContent(),/下次跟进补充签收凭证/);
 await page.locator('#history-revision').fill('1');await page.locator('#history-form button').click();await page.locator('#history-state').filter({hasText:'第 1 版'}).waitFor();
 for(const text of ['INTERNAL_ONLY','INTERNAL_CONTACT','交货与付款约定','下次跟进补充签收凭证'])assert.equal((await page.locator('#history-content').textContent()).includes(text),false);
 assert.match(await page.locator('#history-content').textContent(),/材料清单：\n尚未填写/);report.checks.push('complete-original-snapshot-history');
 await page.locator('#record-title').scrollIntoViewIfNeeded();await capture('intake-wide.png');
 await page.locator('[name=client_reply]').scrollIntoViewIfNeeded();await capture('intake-audiences.png');
 const win=await app.browserWindow(page);report.viewports=[];
 for(const factor of [1,1.5]){await win.evaluate((w,f)=>{w.setSize(760,760);w.webContents.setZoomFactor(f);},factor);await page.locator('#record-title').scrollIntoViewIfNeeded();await capture('intake-small-'+factor+'.png');const size=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));report.viewports.push(size);assert.ok(size.scroll<=size.width+1);}
 await win.evaluate(w=>{w.setSize(1440,1000);w.webContents.setZoomFactor(1);});
 await page.getByRole('link',{name:'返回我的接待'}).click();const b=await create('合成接待乙：独立咨询','乙原话：另一项咨询。');
 assert.equal(await page.locator('[name=client_reply]').inputValue(),'');assert.equal(await page.locator('[name=internal_notes]').inputValue(),'');
 assert.equal((await page.locator('#source-text').innerText()).includes('甲原话'),false);
 await page.getByRole('link',{name:'返回我的接待'}).click();await page.getByRole('link',{name:'合成接待甲：买卖货款',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('[name=client_reply]').value.includes('请补充'));
 report.checks.push('full-page-intake-switch-isolation');
 await page.locator('#convert-panel summary').click();await page.locator('#convert-form [name=objective]').fill('仅合成材料流程验证');await page.locator('#convert-form [name=material_mode]').selectOption('synthetic');
 await page.locator('#convert-form button').click();await page.waitForURL(/\/matters\/[a-f0-9-]+$/);const mid=page.url().split('/').pop();report.convertedMatter=mid;
 await page.goto(new URL('/intakes/'+a,page.url()).href);await page.locator('#converted-notice').waitFor({state:'visible'});assert.equal(await page.locator('#intake-form [name=title]').isDisabled(),true);
 report.checks.push('ui-convert-existing-contract-engine','converted-snapshot-readonly');
 assert.deepEqual(errors,[]);report.consoleErrors=errors;await app.close();app=null;
 app=await launch();page=await app.firstWindow();await login();const records=(await api('/api/intakes')).data.items;
 assert.equal(records.find(x=>x.id===a).matter_id,mid);assert.ok(records.some(x=>x.id===b));
 const matters=(await api('/api/matters')).data;for(const old of oldMatters)assert.ok(matters.some(x=>x.id===old.id));
 report.checks.push('restart-retains-intakes-and-old-cases');report.status='PASS';
 }catch(error){report.status='FAIL';report.error=error.stack;if(page&&!page.isClosed())await capture('failure.png').catch(()=>{});throw error;}
 finally{if(app)await app.close();report.finished=new Date().toISOString();fs.writeFileSync(path.join(output,'intake-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})().catch(error=>{console.error(error);process.exitCode=1;});
