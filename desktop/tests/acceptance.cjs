// Actual Electron window + owned Python process. Synthetic isolated data only.
const { _electron } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const repo = path.resolve(__dirname,'../..');
const output = path.resolve(process.argv[2]);
fs.mkdirSync(output,{recursive:true});
const executable = process.argv[3] || path.join(repo,'desktop/node_modules/electron/dist/electron.exe');
const packaged = Boolean(process.argv[3]);
const data = path.join(output,'中文 用户资料');
const launch = () => _electron.launch({executablePath:executable,args:packaged?[]:[path.join(repo,'desktop')],
  cwd:repo,env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
const report = {packaged,checks:[],started:new Date().toISOString()};
let application, page;
async function capture(name) {
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const window = await application.browserWindow(page);
  const png = await window.evaluate(async win=>(await win.webContents.capturePage()).toPNG().toString('base64'));
  fs.writeFileSync(path.join(output,name),Buffer.from(png,'base64'));
}
async function call(url, body) {
  return page.evaluate(async ({url,body})=>{
    const token = document.cookie.split('; ').find(x=>x.startsWith('qx_csrf='))?.slice(8);
    const response = await fetch(url,{method:body?'POST':'GET',credentials:'same-origin',headers:body?
      {'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(token),'Idempotency-Key':crypto.randomUUID()}:{},body:body?JSON.stringify(body):undefined});
    const result = await response.json();
    if(!response.ok) throw new Error(JSON.stringify({url,status:response.status,result})); return result;
  },{url,body});
}
async function login() {
  await page.waitForURL(/127\.0\.0\.1:\d+\/login/, {timeout:45000});
  await page.locator('[name=username]').fill('桌面合成律师');
  await page.locator('[name=password]').fill('fiction123');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.waitForURL(/127\.0\.0\.1:\d+\/$/);
}
(async()=>{
 try {
  let began=Date.now(); application=await launch();page=await application.firstWindow();
  const consoleErrors=[];page.on('pageerror',error=>consoleErrors.push(error.message));
  await page.locator('#setup').waitFor({state:'visible',timeout:30000});
  await application.evaluate(({Menu})=>Menu.getApplicationMenu().items[0].submenu.items.find(x=>x.label==='重新打开工作台').click());
  assert.equal((await page.evaluate(()=>window.desktopSetup.state())).mode,'setup');
  report.checks.push('restart-menu-before-account');
  await capture('setup.png');
  await page.locator('#username').fill('桌面合成律师');
  await page.locator('#password').fill('fiction123');await page.locator('#confirm').fill('different1');
  await page.locator('#setup button[type=submit]').click();
  await page.locator('#validation').waitFor({state:'visible'});
  assert.match(await page.locator('#validation').innerText(),/不一致/);
  await page.locator('#confirm').fill('fiction123');
  await page.locator('#setup button[type=submit]').click();
  await login();report.startupIncludingSetupMs=Date.now()-began;report.checks.push('setup-password-confirmation','login');
  assert.equal(await page.evaluate(()=>typeof require),'undefined');
  assert.equal(await page.evaluate(()=>window.desktopSetup.state()),null);
  report.checks.push('node-disabled','setup-ipc-denied-to-business-page');
  await page.locator('[name=title]').fill('Windows 桌面合成合同验收');
  await page.locator('#create-form button[type=submit]').click();
  await page.waitForURL(/\/matters\/[a-f0-9-]+$/);
  const matter=page.url().split('/').pop(),base='/api/matters/'+matter;
  await page.locator('input[type=file]').setInputFiles(path.join(repo,'tests/fixtures/assisted-v1/sales-01.docx'));
  await page.locator('#upload-form button[type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#documents')?.innerText.includes('sales-01.docx'),{timeout:30000});
  await page.getByRole('link',{name:'进入原文与事实确认'}).click();
  await page.locator('#anchors .anchor').first().waitFor();
  const details=await call(base);const version=details.documents[0];
  const anchors=await call(base+'/documents/'+version.id+'/anchors');
  const numeric=anchors.anchors.find(a=>a.quote.includes('14067'));
  assert.ok(numeric);report.checks.push('ui-create-case','ui-import-docx','original-anchor');
  await capture('original.png');
  const fact=page.locator('#candidate-fact-form');
  await fact.locator('[name=value]').fill('14067');await fact.locator('[name=unit]').fill('元');
  await fact.locator('[name=anchor_id]').selectOption(numeric.id);await fact.locator('button').click();
  await page.locator('#facts [name=decision]').waitFor();
  await page.locator('#facts [name=decision]').selectOption('confirmed');
  await page.locator('#facts-form button').click();
  await page.waitForFunction(()=>document.querySelector('#message')?.innerText.includes('事实已保存'));
  const context=await call(base+'/review-context'),facts=await call(base+'/facts');
  const submitted=await call(base+'/review-proposals',{context_sha256:context.context_sha256,fact_version:facts.version,
    document_hashes:{[version.id]:version.sha256},examined_anchor_ids:[numeric.id],opinions:[{
      coverage_ids:['C06'],issue_type:'desktop_fixture',severity:'low',evidence_state:'unconfirmed',anchor_ids:[numeric.id],
      analysis:'桌面验收合成意见：核对价款口径。',business_effect:'仅验证工作稿处理。',recommendation:'逐项核对金额和付款凭据。',
      basis_kind:'material_observation',authority_refs:[],unknowns:['本轮不验证真实法律结论。']} ]});
  const run=await call(base+'/reviews/'+submitted.id);
  await call(base+'/findings/'+run.findings[0].id+'/decision',{run_id:run.id,run_sha256:run.run_sha256,decision:'accept',reason:'独立虚构材料验收，已核对原文。'});
  await page.goto(new URL('/matters/'+matter+'/exports',page.url()).href);
  await page.locator('#finding-choice option').first().waitFor({state:'attached'});
  await page.locator('#preview-form button').click();
  const link=page.locator('#bundles a').first();await link.waitFor({timeout:30000});
  const exportPath=path.join(output,'合成工作稿.docx');
  const saved=application.evaluate(({BrowserWindow},target)=>new Promise(resolve=>{
    BrowserWindow.getAllWindows()[0].webContents.session.once('will-download',(_event,item)=>{
      item.setSavePath(target);item.once('done',(_event,state)=>resolve(state));
    });
  }),exportPath);
  await link.click();assert.equal(await saved,'completed');
  const bytes=fs.readFileSync(exportPath);assert.equal(bytes.subarray(0,2).toString(),'PK');
  report.export={bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex')};
  report.checks.push('ui-fact-candidate-and-confirm','api-opinion-and-disposition','ui-preview','authenticated-docx-download');
  await capture('exports.png');
  const appWindow=await application.browserWindow(page);
  const sizes=[];
  for(const factor of [1,1.25,1.5]){
    await appWindow.evaluate((window,factor)=>{window.setSize(760,760);window.webContents.setZoomFactor(factor);},factor);
    await capture('window-'+factor+'.png');
    sizes.push(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,height:innerHeight,zoom:devicePixelRatio})));
  }
  report.windowChecks=sizes;report.consoleErrors=consoleErrors;
  const origin=new URL(page.url()).origin;
  await application.close();application=null;
  await assert.rejects(fetch(origin+'/login'));
  began=Date.now();application=await launch();page=await application.firstWindow();await login();
  report.restartToLoginAndSubmitMs=Date.now()-began;
  assert.ok((await call('/api/matters')).some(m=>m.id===matter));
  assert.deepEqual((await call(base+'/documents/'+version.id+'/anchors')).anchors,anchors.anchors);
  report.checks.push('owned-server-stopped','restart-keeps-case-and-anchors');
  report.status='PASS';
 } catch(error){report.status='FAIL';report.error=error.stack;if(page&&!page.isClosed()){report.pageText=await page.locator('body').innerText();await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});}throw error;}
 finally{
  if(application)await application.close();
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({status:report.status,checks:report.checks.length,output}));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
