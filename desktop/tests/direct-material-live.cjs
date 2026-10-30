// Opt-in, actual source Electron + real provider; independent fictional data only.
// Credential remains an OS-encrypted blob, is never logged, and the temporary copy is removed.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const repo=path.resolve(__dirname,'../..'),output=path.resolve(process.argv[2]||'');
const model=process.env.QX_LIVE_MODEL||'deepseek-v4-pro';
assert.ok(['deepseek-flash','deepseek-v4-pro'].includes(model));
const fixture=process.argv[4]?path.resolve(process.argv[4]):path.join(repo,'tests/fixtures/assisted-v1/sales-01.docx');
assert.equal(process.argv[3],'--live','Explicit --live is required; never run this in ordinary CI.');
assert.ok(process.env.QX_LIVE_CREDENTIAL_SOURCE,'An existing OS-encrypted DeepSeek credential path is required.');
const resume=process.env.QX_LIVE_RESUME==='1';
assert.ok(resume?fs.existsSync(path.join(output,'report.json')):!fs.existsSync(output),
  'Use a fresh isolated output directory, or explicitly resume saved successful work.');
const source=path.resolve(process.env.QX_LIVE_CREDENTIAL_SOURCE);
assert.equal(path.basename(source),'deepseek.bin');
assert.ok(fs.statSync(source).isFile()&&!fs.lstatSync(source).isSymbolicLink());
const data=path.join(output,'synthetic-data'),credential=path.join(data,'model-credentials','deepseek.bin');
const digest=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const sourceHash=digest(source);
fs.mkdirSync(path.dirname(credential),{recursive:true});fs.copyFileSync(source,credential,fs.constants.COPYFILE_EXCL);
// Chromium's encrypted wrapping key is profile-bound. Copy only its protected
// metadata, never the original profile, cookies, settings, or decrypted secret.
const protection=JSON.parse(fs.readFileSync(path.join(path.dirname(path.dirname(source)),'Local State'),'utf8')).os_crypt;
assert.equal(typeof protection?.encrypted_key,'string');
const localState=path.join(data,'Local State');
fs.writeFileSync(localState,JSON.stringify({os_crypt:{encrypted_key:protection.encrypted_key,
  ...(typeof protection.audit_enabled==='boolean'?{audit_enabled:protection.audit_enabled}:{})}}),{flag:'wx'});
const report=resume?JSON.parse(fs.readFileSync(path.join(output,'report.json'),'utf8')):
  {started:new Date().toISOString(),status:'RUNNING',mode:'source-electron-real-provider',
    synthetic_only:true,checks:[],attempts:[],material_posts:0};
if(resume){assert.ok(report.attempts.length>=1);assert.equal(report.attempts[0].state,'received');
  report.resumed=new Date().toISOString();delete report.error;delete report.page;}
let app,page;const errors=[];
async function login(){
  await page.waitForURL(/\/login$/,{timeout:60000});
  await page.locator('[name=username]').fill('虚构模型验收律师');await page.locator('[name=password]').fill('fiction123');
  await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL(/\/assistant$/);
}
async function upload(file){
  await page.locator('#add-material').click();await page.locator('#material-file').setInputFiles(file);
  assert.equal(await page.locator('#material-consent,#material-purpose').count(),0);
  await page.locator('#composer').press('Enter');
  await page.waitForFunction(name=>document.querySelector('#material-list').textContent.includes(name),path.basename(file));
  // Use explicit awaited reads; do not treat a Promise in a DOM predicate as a completed parse.
  for(let n=0;n<30;n++){
    const ready=await page.evaluate(async()=>{const id=location.pathname.split('/').pop();
      const r=await fetch('/api/assistant/conversations/'+id+'/materials');if(!r.ok)return false;
      const v=await r.json();return v.items.length>0&&v.items.every(item=>item.parse_revision>0);});
    if(ready)return;
    await new Promise(resolve=>setTimeout(resolve,1000));
  }
  throw Error('Automatic material reading did not complete.');
}
async function send(prompt){
  const before=report.material_posts;
  await page.locator('#composer').fill(prompt);
  const submitted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/material-generations'),{timeout:45000});
  await page.locator('#send').click();
  const response=await submitted;assert.equal(response.status(),202,await response.text());
  const pending=await response.json();
  const cid=pending.scope.conversation_id;
  let attempt=pending;
  const expires=Date.now()+120000;
  while(Date.now()<expires){
    await new Promise(resolve=>setTimeout(resolve,1000));
    attempt=await page.evaluate(async id=>{const reply=await fetch('/api/assistant/attempts/'+id);
      return reply.ok?await reply.json():null;},pending.id);
    if(['received','sent_unknown','failed_before_send'].includes(attempt?.state))break;
  }
  report.attempts.push({id:attempt.id,conversation_id:cid,state:attempt.state,receipt:attempt.receipt,
    workflow:attempt.output?.manifest.workflow,has_output:!!attempt.output,text_length:attempt.output?.candidate.text.length||0,
    citations:attempt.output?.candidate.citations.length||0,history_pairs:(attempt.output?.manifest.conversation_history?.length||0)/2});
  assert.equal(attempt.state,'received');assert.ok(attempt.output?.candidate.text.length>100,'A real saved draft is required.');
  assert.equal(attempt.output.review_status,'unverified');assert.equal(report.material_posts,before+1);
  await page.locator('.generation-result[data-attempt-id="'+attempt.id+'"] .generation-text').first().waitFor({timeout:30000});
  assert.ok(page.url().includes('/assistant/'));assert.equal((await app.windows()).length,1,'No per-send approval window in configured scope.');
  return attempt;
}
async function saved(workflow,index=0){
  const record=report.attempts.filter(item=>item.workflow===workflow&&item.has_output)[index];
  return record?await page.evaluate(async id=>(await fetch('/api/assistant/attempts/'+id)).json(),record.id):null;
}
async function showConversation(id){
  await page.locator('[data-conversation-id="'+id+'"]').click();
  await page.waitForURL('**/assistant/'+id);
}
(async()=>{try{
  app=await _electron.launch({executablePath:path.join(repo,'desktop/node_modules/electron/dist/electron.exe'),
    args:[path.join(repo,'desktop')],cwd:repo,env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
  page=await app.firstWindow();page.setDefaultTimeout(30000);
  await page.addInitScript(()=>window.addEventListener('beforeunload',event=>event.stopImmediatePropagation(),true));
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/material-generations'))report.material_posts++;});
  if(!resume){await page.locator('#setup').waitFor({timeout:60000});
  await page.locator('#username').fill('虚构模型验收律师');await page.locator('#password').fill('fiction123');
  await page.locator('#confirm').fill('fiction123');await page.locator('#setup button[type=submit]').click();
  }
  await login();if(!resume)report.checks.push('fresh-synthetic-workspace-login');
  if(!resume){
  await app.evaluate(({Menu})=>Menu.getApplicationMenu().items.flatMap(item=>item.submenu?.items||[])
    .find(item=>item.label==='主模型设置…').click());
  await page.locator('#model-settings').waitFor();
  await page.waitForFunction(()=>!document.querySelector('#model-id').disabled);
  assert.equal(await page.locator('#model-automatic-analysis').isChecked(),false);
  await page.locator('#model-id').selectOption(model);
  await page.locator('#model-configure').click();
  await page.waitForFunction(()=>document.querySelector('#model-runtime-status').textContent.includes('已配置'));
  assert.equal(await page.locator('#model-automatic-analysis').isChecked(),false);
  await page.locator('#resume').click();await page.waitForURL(/\/assistant$/);report.checks.push('initial-native-range-configured');
  await upload(fixture);
  }
  let first;
  if(resume){
    await showConversation(report.attempts[0].conversation_id);
    first=await page.evaluate(async id=>(await fetch('/api/assistant/attempts/'+id)).json(),report.attempts[0].id);
    assert.equal(first.state,'received');assert.ok(first.output);report.checks.push('restart-reads-original-success-without-resending');
  }else first=await send('我是甲方，帮我审查并给出最小修改建议。材料是完全虚构的验收样本。');
  assert.equal(first.output.manifest.workflow,'contract');report.checks.push('one-send-real-contract-draft-in-chat');
  fs.writeFileSync(path.join(output,'contract-draft.txt'),first.output.candidate.text,'utf8');
  const url='/api/assistant/conversations/'+first.scope.conversation_id+'/material-generations/'+first.id+'/document';
  const downloaded=await page.evaluate(async url=>{const r=await fetch(url);
    return {status:r.status,bytes:r.ok?Array.from(new Uint8Array(await r.arrayBuffer())):[]};},url);
  assert.equal(downloaded.status,200);fs.writeFileSync(path.join(output,'contract-draft.docx'),Buffer.from(downloaded.bytes));
  report.checks.push('editable-docx-from-saved-result');
  if(process.env.QX_LIVE_SCENARIOS==='all'){
    const followup=await saved('contract',1)||await send('把上次建议中的付款条款改成可以直接替换的文本，保留甲方立场，简洁回答。');
    assert.equal(followup.output.manifest.stable_task_id,first.output.manifest.stable_task_id);
    assert.equal(followup.output.manifest.conversation_history.length,2);report.checks.push('same-task-followup-uses-saved-answer');
    let sales=await saved('sales');
    if(sales)await showConversation(sales.scope.conversation_id);
    else {await page.locator('#new-conversation').click();
      sales=await send('客户咨询：完全虚构的客户林女士称，9月3日为公司付了10万元采购10台扫描设备，10月8日只收到6台，其中2台无法启动。想要补货和修理。请整理接待底稿、待问问题、给客户的回复草稿和跟进事项。');}
    assert.equal(sales.output.manifest.workflow,'sales');assert.equal(sales.output.manifest.materials.length,0);
    assert.equal(sales.output.manifest.conversation_history?.length||0,0);report.checks.push('sales-draft-no-other-chat-materials');
    let caseDraft=await saved('case');
    if(!caseDraft){await upload(fixture);await upload(path.join(path.dirname(fixture),'虚构案件陈述与凭证.docx'));
      caseDraft=await send('整理这个案件并起草起诉状，依据当前全部虚构材料，请求补交4台并修理故障设备，缺项用待补占位。');}
    assert.equal(caseDraft.output.manifest.workflow,'case');report.checks.push('case-timeline-and-pleading-draft');
    const court=await saved('court')||await send('根据现有材料模拟开庭，只选两个主要争点，各用对方律师、法官、己方应对三个视角简短推演，最后给出三项庭前准备清单，总长不超过900字。');
    assert.equal(court.output.manifest.workflow,'court');
    assert.deepEqual(court.output.manifest.materials,caseDraft.output.manifest.materials);report.checks.push('court-reuses-case-materials');
    for(const [name,attempt] of [['followup',followup],['sales',sales],['case',caseDraft],['court',court]])
      fs.writeFileSync(path.join(output,name+'-draft.txt'),attempt.output.candidate.text,'utf8');
  }
  await page.screenshot({path:path.join(output,'contract-result.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>typeof require),'undefined');
  report.checks.push('no-renderer-node-or-page-errors');report.status='PASS';
}catch(error){report.status='FAIL';report.error=String(error.stack);
  if(page&&!page.isClosed()){report.page=await page.locator('body').innerText().catch(()=>null);
    await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});}
  process.exitCode=1;
}finally{
  if(app)await app.close().catch(()=>{});
  if(fs.existsSync(credential))fs.unlinkSync(credential);
  if(fs.existsSync(localState))fs.unlinkSync(localState);
  assert.equal(digest(source),sourceHash,'Original encrypted credential must remain unchanged.');
  report.finished=new Date().toISOString();report.temporary_credential_removed=!fs.existsSync(credential);
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({status:report.status,checks:report.checks,attempts:report.attempts,material_posts:report.material_posts,error:report.error}));
}})();
