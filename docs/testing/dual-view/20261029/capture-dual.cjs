const fs=require('node:fs'),path=require('node:path');
const {chromium}=require('/Users/molin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const f=JSON.parse(fs.readFileSync('/private/tmp/qx-ui-dual-view-20261029/preview.json','utf8'));
 const out='/Users/molin/Documents/ChatGPT/AI律所项目/outputs/双视图工作台_20261029';fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const report={screenshots:[],page_errors:[],external_requests:[],scope:f.scope};
 try{
  const context=await browser.newContext({viewport:{width:1440,height:900}});
  await context.route('**/*',route=>route.request().url().startsWith(f.origin+'/')?route.continue():(report.external_requests.push(route.request().url()),route.abort()));
  const result=await context.request.post(f.origin+'/api/login',{data:{username:'界面演示律师',password:'preview123'}});if(result.status()!==200)throw Error('login');
  const p=await context.newPage();p.on('pageerror',e=>report.page_errors.push(e.message));
  const frames=()=>p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const shot=async(name)=>{await frames();await p.screenshot({path:path.join(out,name)});report.screenshots.push(name);};
  const mode=async(v)=>{await p.locator('#view-mode-'+v).click();await p.waitForFunction(v=>document.body.dataset.viewMode===v,v);await frames();};
  const tool=async(id)=>{if(!await p.locator('#conversation-tools').evaluate(e=>e.open))await p.locator('#conversation-tools-summary').click();await p.locator('#'+id).click();};
  await p.goto(f.origin+'/assistant');await p.locator('#save-status').filter({hasText:'尚未输入'}).waitFor();
  await p.waitForFunction(()=>[...document.images].every(i=>i.complete));await shot('01_工作台首页.png');
  await mode('chat');await shot('02_对话首页.png');
  await p.goto(f.origin+'/assistant/'+f.cid);await p.locator('#history article').first().waitFor();
  if(await p.locator('#material-list .material-row').count()===0){await p.locator('#add-material').click();await p.locator('#material-file').setInputFiles(path.join(f.base,'虚构借贷事项.docx'));await p.locator('#material-consent').check();await p.locator('#upload-material').click();await p.locator('#material-list').filter({hasText:'读取版本 1'}).waitFor();}
  await mode('chat');await p.locator('#conversation-thread').evaluate(e=>e.scrollTop=0);await shot('03_对话与材料.png');
  await p.locator('#conversation-tools-summary').click();await shot('04_事项工具菜单.png');await p.locator('#show-followups').click();await p.waitForFunction(()=>!document.getElementById('followup-title').disabled&&document.activeElement.id==='followup-panel');await shot('05_对话中的跟进清单.png');await p.locator('#close-chat-workarea').click();
  await tool('show-outputs');await p.locator('#output-source option').nth(1).waitFor({state:'attached'});await p.locator('#output-source').selectOption('0');await p.locator('#output-audience').selectOption('client');await p.locator('#output-preview').click();await p.locator('#output-result').waitFor({state:'visible'});await shot('06_对话中的成果预览.png');await p.locator('#close-outputs').click();
  await p.setViewportSize({width:390,height:844});await frames();await shot('07_窄屏对话.png');
  await p.setViewportSize({width:1224,height:785});await p.goto(f.origin+'/assistant');await p.locator('#save-status').filter({hasText:'尚未输入'}).waitFor();await mode('chat');await shot('08_普通窗口对话首页.png');
  report.pass=report.page_errors.length===0&&report.external_requests.length===0;fs.writeFileSync(path.join(out,'capture-final.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
