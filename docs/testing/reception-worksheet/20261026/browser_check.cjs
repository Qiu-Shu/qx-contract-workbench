const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('/Users/molin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
const output=fs.readFileSync('/tmp/qx-worksheet-browser-path','utf8').trim(),fixture=JSON.parse(fs.readFileSync(path.join(output,'fixture.json'),'utf8'));
const origin='http://127.0.0.1:18770',source='甲称借出10万元，乙称部分已还，目前没有完整还款凭证。';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{
const context=await browser.newContext({viewport:{width:1280,height:900},acceptDownloads:true});
assert.equal((await context.request.post(origin+'/api/login',{data:{username:'合成接待律师',password:'fiction123'}})).status(),200);
const page=await context.newPage(),errors=[],external=[],requests=[];
page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{requests.push({method:r.method(),url:r.url()});if(!r.url().startsWith(origin))external.push(r.url());});
await page.goto(origin+'/assistant/'+fixture.cid);
await page.getByRole('textbox',{name:'咨询内容与工作草稿',exact:true}).fill(source);
await page.getByRole('button',{name:'保存草稿',exact:true}).click();
await page.getByRole('button',{name:'接待底稿',exact:true}).click();
await page.locator('#worksheet-notes').filter({hasText:''}).waitFor({state:'visible'});
await page.waitForFunction(()=>!document.getElementById('worksheet-notes').disabled);
assert.match(await page.locator('#worksheet-notes').inputValue(),/原内部备注/);
await page.getByRole('button',{name:'追加输入框文字到原始陈述',exact:true}).click();
await page.getByRole('button',{name:'保留原备注并插入底稿提纲',exact:true}).click();
const notes='原内部备注：谈判安排只供律师核对。\n客户诉求：核清款项\n我方立场：尚未确定代理哪一方\n已知陈述（待核）：乙称部分已还\n待核问题：金额、时间、方式和凭证\n下一步：补材料';
await page.locator('#worksheet-notes').fill(notes);
const location=page.url();await page.getByRole('button',{name:'新对话',exact:true}).click();assert.equal(page.url(),location);
await page.getByRole('button',{name:'保存底稿',exact:true}).click();
await page.getByText('已确认保存回执，人工修改与明确清空受保护；内容仍待核验。',{exact:true}).waitFor();
await page.getByRole('button',{name:'查看本地模板追问',exact:true}).click();
const card=page.locator('#worksheet-suggestions section').filter({hasText:'所称还款分别在什么时间'});
await card.getByRole('button',{name:'采用此追问',exact:true}).click();
assert.match(await page.locator('#worksheet-questions').inputValue(),/金额/);
assert.match(await page.locator('#worksheet-materials').inputValue(),/还款记录/);
await page.getByRole('button',{name:'保存底稿',exact:true}).click();
await page.getByText('已确认保存回执，人工修改与明确清空受保护；内容仍待核验。',{exact:true}).waitFor();
await page.locator('#worksheet-client-reply').fill('您好，请补充完整还款记录，金额仍需核对。');
await page.getByRole('button',{name:'保存底稿',exact:true}).click();
await page.getByText('已确认保存回执，人工修改与明确清空受保护；内容仍待核验。',{exact:true}).waitFor();
let commits=0,receiptReads=0;
await page.route('**/reception-worksheet/commits',async route=>{commits++;const result=await route.fetch();assert.equal(result.status(),200);await route.abort('failed');});
page.on('request',r=>{if(r.url().includes('/reception-worksheet/receipts/'))receiptReads++;});
await page.locator('#worksheet-notes').fill(notes+'\n后续补充：继续核对，不直接认定余额。');
await page.getByRole('button',{name:'保存底稿',exact:true}).click();
await page.getByRole('button',{name:'查询本次保存回执',exact:true}).waitFor();
await page.getByRole('button',{name:'查询本次保存回执',exact:true}).click();
await page.getByText('已确认保存回执，人工修改与明确清空受保护；内容仍待核验。',{exact:true}).waitFor();
await page.unroute('**/reception-worksheet/commits');assert.equal(commits,1);assert.equal(receiptReads,1);
await page.getByRole('button',{name:'准备AI追问 · 待核对发送',exact:true}).click();
await page.getByText('任务已放入并保存为输入框草稿，尚未发送或调用模型。请核对全文后发送；回答完成后可重新读取底稿查看候选。',{exact:true}).waitFor();
const prepared=await page.locator('#composer').inputValue();assert.ok(prepared.startsWith('【接待追问任务：借贷咨询】'));assert.ok(prepared.includes(source)&&prepared.includes(notes));
assert.equal(requests.filter(r=>r.method==='POST'&&/\/(profile-generations|generations|context-generations)$/.test(r.url)).length,0);
await page.reload();await page.getByRole('button',{name:'接待底稿',exact:true}).click();await page.waitForFunction(()=>!document.getElementById('worksheet-notes').disabled);
assert.match(await page.locator('#worksheet-notes').inputValue(),/后续补充/);assert.equal(await page.locator('#worksheet-source').inputValue(),source);
await page.locator('#worksheet-notes').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'worksheet-1280.png')});
await page.setViewportSize({width:390,height:844});await page.locator('#worksheet-questions').scrollIntoViewIfNeeded();
assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
await page.screenshot({path:path.join(output,'worksheet-390.png')});
await page.setViewportSize({width:1280,height:900});await page.getByRole('button',{name:'成果与导出',exact:true}).click();
await page.locator('#output-source option[value="0"]').waitFor({state:'attached'});await page.getByLabel('已保存成果',{exact:true}).selectOption('0');
await page.getByLabel('接收对象',{exact:true}).selectOption('client');await page.getByRole('button',{name:'预览所选版本',exact:true}).click();
await page.locator('#output-text').filter({hasText:'您好，请补充完整还款记录'}).waitFor();
assert.equal((await page.locator('#output-panel').innerText()).includes('谈判安排'),false);
const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出 Word',exact:true}).click();await(await download).saveAs(path.join(output,'worksheet-client.docx'));
assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
fs.writeFileSync(path.join(output,'browser-report.json'),JSON.stringify({ok:true,manual_statement:true,prior_notes_retained:true,
 template_adopted_explicitly:true,unsaved_navigation_blocked:true,lost_ack:{posts:commits,receipt_gets:receiptReads},
 prepared_but_not_sent:true,reopened:true,mobile_no_overflow:true,customer_docx:true,page_errors:errors,external_requests:external,
 worksheet_requests:requests.filter(r=>r.url.includes('/reception-worksheet')),generation_posts:requests.filter(r=>r.method==='POST'&&/generations$/.test(r.url))},null,2));
console.log(JSON.stringify({ok:true,output,commits,receiptReads}));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
