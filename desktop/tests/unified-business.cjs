// Actual packaged Electron + owned backend; isolated synthetic data only.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const repo=path.resolve(__dirname,'../..'),output=path.resolve(process.argv[2]);
const executable=process.argv[3]||path.join(repo,'desktop/node_modules/electron/dist/electron.exe');
const packaged=!!process.argv[3],data=path.join(output,'中文 用户资料');
fs.mkdirSync(output,{recursive:true});
const launch=()=>_electron.launch({executablePath:executable,args:packaged?[]:[path.join(repo,'desktop')],cwd:repo,
  env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
const report={packaged,checks:[],started:new Date().toISOString()};
let app,page;const errors=[],external=[],modelPosts=[],apiResponses=[];
async function closeApp(){
  if(!app)return;
  // Synthetic teardown must not be masked by Playwright's beforeunload dialog race.
  if(page&&!page.isClosed())await page.evaluate(()=>window.addEventListener('beforeunload',event=>event.stopImmediatePropagation(),true)).catch(()=>{});
  await app.close();app=null;
}
async function login(){
  page=await app.firstWindow();page.setDefaultTimeout(30000);
  await page.addInitScript(()=>window.addEventListener('beforeunload',event=>event.stopImmediatePropagation(),true));
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{if(response.url().includes('/api/task-executions/'))apiResponses.push({url:response.url(),status:response.status()});});
  page.on('request',request=>{const url=new URL(request.url());
    if(/^https?:$/.test(url.protocol)&&url.hostname!=='127.0.0.1')external.push(url.origin);
    if(request.method()==='POST'&&/model|generate/.test(url.pathname))modelPosts.push(url.pathname);
  });
  await page.waitForURL(/\/login$/,{timeout:60000});
  await page.locator('[name=username]').fill('桌面合成律师');
  await page.locator('[name=password]').fill('fiction123');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.waitForURL(/\/assistant$/);await page.locator('#composer').waitFor();
}
async function send(text){
  await page.locator('#composer').fill(text);await page.locator('#send').click();
  await page.waitForFunction(()=>document.querySelector('#composer').value==='');
}
(async()=>{try{
  app=await launch();page=await app.firstWindow();
  await page.addInitScript(()=>window.addEventListener('beforeunload',event=>event.stopImmediatePropagation(),true));
  await page.locator('#setup').waitFor({timeout:60000});
  await page.locator('#username').fill('桌面合成律师');await page.locator('#password').fill('fiction123');
  await page.locator('#confirm').fill('fiction123');await page.locator('#setup button[type=submit]').click();
  await login();report.checks.push('packaged-setup-login-and-unified-home');
  await send('帮我审查这个合同');
  await page.locator('#task-current').waitFor();
  await page.waitForFunction(()=>document.querySelector('#task-current').textContent.includes('帮我审查这个合同'));
  const taskId=await page.locator('#task-select').inputValue();assert.ok(taskId);
  report.checks.push('natural-contract-intent-creates-task');
  const source=path.join(repo,'tests/fixtures/assisted-v1/sales-01.docx');
  await page.locator('#add-material').click();await page.locator('#material-file').setInputFiles(source);
  await page.locator('#material-purpose').selectOption('synthetic');
  await page.locator('#material-consent').check();await page.locator('#upload-material').click();
  await page.waitForFunction(name=>document.querySelector('#material-list').textContent.includes(name),path.basename(source));
  await send('补充主合同，请继续审查');assert.equal(await page.locator('#task-select').inputValue(),taskId);
  report.checks.push('local-material-upload-and-supplement-keep-task');
  await page.getByRole('button',{name:'冻结材料',exact:true}).click();
  await page.getByLabel('档案名称',{exact:true}).fill('打包版统一聊天合成审查');
  await page.getByLabel('合同类型',{exact:true}).selectOption('sales');
  await page.getByLabel('我方角色',{exact:true}).selectOption('buyer');
  await page.getByLabel('合同状态',{exact:true}).selectOption('pre_sign');
  const [prepareResponse]=await Promise.all([
    page.waitForResponse(response=>response.url().includes('/create-and-prepare'),{timeout:30000}),
    page.getByRole('button',{name:'保存档案并读取事实',exact:true}).click()
  ]);
  assert.equal(prepareResponse.status(),200);
  await page.getByText('核对事实 · 当前第 1 版',{exact:true}).click();
  for(const select of await page.locator('#task-current fieldset select').all())await select.selectOption('confirmed');
  for(const input of await page.locator('#task-current fieldset input').all())await input.fill('验收人员核对独立虚构样本');
  await page.getByRole('button',{name:'保存本次事实核对',exact:true}).click();
  await page.getByText('核对事实 · 当前第 2 版',{exact:true}).waitFor();
  await page.getByRole('button',{name:'运行模拟审查',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#task-current').textContent.includes('本次模拟审查结果'),{timeout:60000});
  report.checks.push('case-fact-decisions-and-mock-review-in-same-chat');
  const conversation=page.url().split('/').pop();
  await closeApp();app=await launch();await login();
  await page.locator('#conversation-list [data-conversation-id="'+conversation+'"]').click();
  await page.waitForFunction(()=>document.querySelector('#task-current').textContent.includes('本次模拟审查结果'));
  assert.equal(await page.locator('#task-select').inputValue(),taskId);
  report.checks.push('actual-restart-retains-task-and-review-result');
  assert.equal(await page.evaluate(()=>typeof require),'undefined');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.deepEqual(modelPosts,[]);
  report.checks.push('no-node-page-errors-external-requests-or-model-posts');report.status='PASS';
}catch(error){report.status='FAIL';report.error=error.stack;report.apiResponses=apiResponses;
  if(page&&!page.isClosed())report.pageText=await page.locator('body').innerText().catch(()=>null);
  if(page&&!page.isClosed())await page.screenshot({path:path.join(output,'unified-business-failure.png'),fullPage:true}).catch(()=>{});
  throw error;
}finally{await closeApp();report.finished=new Date().toISOString();
  fs.writeFileSync(path.join(output,'unified-business-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})().catch(error=>{console.error(error);process.exitCode=1;});
