// Run acceptance.cjs with the previous installed binary in this output first.
// Only independent synthetic data; never point this at a user's data directory.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const [outputArg,executable]=process.argv.slice(2),output=path.resolve(outputArg);
const data=path.join(output,'中文 用户资料'),report={checks:[],started:new Date().toISOString()};
assert.equal(JSON.parse(fs.readFileSync(path.join(output,'report.json'),'utf8')).status,'PASS');
const protectedRoot=path.join(data,'workspaces/main/protected');
function hashes(root){
  const result={};
  for(const name of fs.readdirSync(root,{recursive:true})){
    const file=path.join(root,name);if(fs.statSync(file).isFile())result[name]=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
  }return result;
}
const originalHashes=hashes(protectedRoot),errors=[],external=[];
assert.ok(Object.keys(originalHashes).length>0);
let app,page,conversation;
const launch=()=>_electron.launch({executablePath:executable,cwd:path.resolve(__dirname,'../..'),
  env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
async function login(){
  page=await app.firstWindow();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(/^https?:/.test(r.url())&&new URL(r.url()).hostname!=='127.0.0.1')external.push(r.url());});
  await page.waitForURL(/\/login$/,{timeout:60000});
  await page.locator('[name=username]').fill('桌面合成律师');await page.locator('[name=password]').fill('fiction123');
  await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL(/\/assistant$/);
  await page.locator('#composer').waitFor();
}
async function get(url){return page.evaluate(async url=>{const r=await fetch(url);if(!r.ok)throw Error('HTTP '+r.status);return r.json();},url);}
(async()=>{try{
  app=await launch();await login();report.version=await app.evaluate(({app})=>app.getVersion());assert.equal(report.version,'0.5.5');
  assert.equal(await page.evaluate(()=>typeof require),'undefined');
  const matters=await get('/api/matters');assert.equal(matters.length,1);
  const matter=await get('/api/matters/'+matters[0].id);assert.ok(matter.documents.length>0);
  const anchors=await get('/api/matters/'+matters[0].id+'/documents/'+matter.documents[0].id+'/anchors');
  assert.ok(anchors.anchors.some(a=>a.quote.includes('14067')));
  for(const [name,hash] of Object.entries(originalHashes))assert.equal(hashes(protectedRoot)[name],hash);
  report.checks.push('old-account-login','old-case-and-anchors-retained','old-protected-files-byte-equal','new-assistant-home-no-node');
  await page.locator('#composer').fill('独立虚构升级咨询：客户称已付款，尚待核对。');
  await page.waitForFunction(()=>document.querySelector('#save-status').textContent==='草稿已保存到本机');
  conversation=page.url().split('/').pop();
  await page.locator('#show-worksheet').click();await page.locator('#worksheet-source').fill('独立虚构升级测试原话，尚待核实。');
  await page.locator('#worksheet-notes').fill('内部合成备注：先核对付款凭证。');
  await page.locator('#worksheet-client-reply').fill('请补充付款凭证供核对。');
  await page.locator('#worksheet-save').click();
  await page.waitForFunction(()=>document.querySelector('#worksheet-version').textContent.includes('已保存档案版本 1'));
  await page.reload();await page.locator('#show-worksheet').click();
  await page.waitForFunction(()=>document.querySelector('#worksheet-source').value==='独立虚构升级测试原话，尚待核实。');
  assert.equal(await page.locator('#worksheet-client-reply').inputValue(),'请补充付款凭证供核对。');
  report.checks.push('merged-reception-worksheet-save-and-reload');
  for(const id of ['show-evidence','show-followups','show-outputs'])assert.equal(await page.locator('#'+id).isEnabled(),true);
  await page.locator('#task-draft-panel > summary').click();await page.getByText('微信收件与离线验证',{exact:true}).click();await page.locator('#weixin-pending-panel > summary').click();
  await page.locator('#weixin-pending-targets').click();
  await page.waitForFunction(()=>document.querySelectorAll('#weixin-pending-target option').length>1);
  assert.match(await page.locator('#weixin-state').textContent(),/未绑定|未配置|未授权|不可用|尚未/);
  report.checks.push('evidence-followup-export-entries','packaged-pending-module-loads-targets');
  const win=await app.browserWindow(page);await win.evaluate(w=>w.setSize(1366,900));
  await page.screenshot({path:path.join(output,'upgraded-desktop.png')});
  const origin=new URL(page.url()).origin;await app.close();app=null;await assert.rejects(fetch(origin+'/login'));
  app=await launch();await login();await page.locator('[data-conversation-id="'+conversation+'"]').click();
  await page.waitForFunction(()=>document.querySelector('#save-status').textContent==='草稿已保存到本机');
  assert.equal(await page.locator('#composer').inputValue(),'独立虚构升级咨询：客户称已付款，尚待核对。');
  report.checks.push('restart-retains-new-draft','owned-backend-stops');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);report.checks.push('no-page-errors-or-browser-external-requests');
  report.status='PASS';
}catch(e){report.status='FAIL';report.error=e.stack;if(page&&!page.isClosed())await page.screenshot({path:path.join(output,'upgrade-failure.png')}).catch(()=>{});throw e;}
finally{if(app)await app.close();report.finished=new Date().toISOString();fs.writeFileSync(path.join(output,'upgrade-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})().catch(e=>{console.error(e);process.exitCode=1;});
