const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {chromium}=require('/Users/molin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const directory='/private/tmp/qx-ui-dual-view-20261029';
const report={started:new Date().toISOString(),checks:[],geometry:[],page_errors:[],external_requests:[],forbidden_model_requests:[],mode_request_windows:[],replays:[]};
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(process.env.QX_ACCEPTANCE_PREVIEW||path.join(directory,'preview-acceptance.json'),'utf8'));
 const cid=fixture.acceptance_cid||fixture.cid;
 const origin=fixture.origin;
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const contexts=[];
 let p,context,restoreDraft=null;
 const requestLog=[];
 async function createContext(options={}){
  const c=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true,...options});contexts.push(c);
  await c.route('**/*',async route=>{
   const request=route.request(),url=request.url();
   if(!url.startsWith(origin+'/')){report.external_requests.push(url);return route.abort();}
   // A UI regression cannot accidentally make a genuine model/research request.
   if(request.method()==='POST'&&/\/(?:generations|business|researches|context-generations|profile-generations|material-generations|cancel)(?:\?|$)/.test(url)){
    report.forbidden_model_requests.push({method:request.method(),url});return route.abort();
   }
   return route.continue();
  });
  const login=await c.request.post(origin+'/api/login',{data:{username:'界面演示律师',password:'preview123'}});
  assert.equal(login.status(),200,'synthetic preview login');return c;
 }
 async function settle(){await p.waitForLoadState('networkidle');await pause(60);}
 async function mode(value){await p.locator('#view-mode-'+value).click();await p.waitForFunction(v=>document.body.dataset.viewMode===v,value);await p.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));}
 async function tools(){const el=p.locator('#conversation-tools');if(!await el.evaluate(e=>e.open))await p.locator('#conversation-tools-summary').click();}
 async function chatAction(id){await mode('chat');await tools();await p.locator('#'+id).click();}
 async function windowOfModeSwitch(label,action){
  await settle();const start=requestLog.length;await action();await pause(240);
  const requests=requestLog.slice(start);report.mode_request_windows.push({label,requests});assert.deepEqual(requests,[],label+' must produce no HTTP requests');
 }
 async function check(name,action){
  try{await action();report.checks.push({name,pass:true});console.log('PASS '+name);}
  catch(error){const item={name,pass:false,error:String(error)};report.checks.push(item);console.log('FAIL '+name+' '+error);
   if(p&&!p.isClosed())try{await p.screenshot({path:path.join(directory,'failure-'+report.checks.length+'.png'),fullPage:true});}catch{}
   if(p&&!p.isClosed())try{await p.setViewportSize({width:1440,height:900});await p.evaluate(()=>document.querySelectorAll('[data-dual-view-replay],[data-dual-material-replay]').forEach(e=>e.remove()));}catch{}
  }
 }
 function parseDocx(file){return execFileSync('/private/tmp/qx-ui-preview-20261029/venv/bin/python',['-c','import sys,zipfile,xml.etree.ElementTree as E; z=zipfile.ZipFile(sys.argv[1]); r=E.fromstring(z.read("word/document.xml")); print("".join(r.itertext()))',file],{encoding:'utf8'});}
 try{
  context=await createContext();p=await context.newPage();p.setDefaultTimeout(10000);
  p.on('pageerror',error=>report.page_errors.push(error.message));
  p.on('request',request=>requestLog.push({method:request.method(),url:request.url().replace(origin,'')}));
  await p.goto(origin+'/assistant/'+cid);await p.locator('#history article').first().waitFor();await settle();
  await check('cold load defaults to workbench and offers accessible mode buttons',async()=>{
   assert.equal(await p.locator('body').getAttribute('data-view-mode'),'workbench');
   assert.equal(await p.locator('#view-mode-workbench').getAttribute('aria-pressed'),'true');
   assert.equal(await p.locator('#view-mode-chat').getAttribute('aria-pressed'),'false');
   await p.locator('#view-mode-chat').focus();await p.keyboard.press('Enter');
   assert.equal(await p.locator('body').getAttribute('data-view-mode'),'chat');
   await mode('workbench');
  });
  await check('normal local upload saves, reads and selects the synthetic Word material',async()=>{
   const before=await p.locator('#material-list .material-row').count();await p.locator('#add-material').click();await p.locator('#material-file').setInputFiles(path.join(fixture.base,'虚构借贷事项.docx'));await p.locator('#material-consent').check();await p.locator('#upload-material').click();await p.waitForFunction(n=>document.querySelectorAll('#material-list .material-row').length>n,before);await p.locator('#material-list .material-row').last().filter({hasText:'读取版本 1'}).waitFor({timeout:15000});await settle();
  });
  await check('mode round trips preserve URL, cid, draft node/value/cursor, history and selected materials without requests',async()=>{
   const original=await p.locator('#composer').inputValue();
   await p.evaluate(()=>{window.__dualView={composer:document.getElementById('composer'),history:document.getElementById('history')};const e=window.__dualView.composer;e.setSelectionRange(Math.min(3,e.value.length),Math.min(9,e.value.length));});
   const snapshot=await p.evaluate(()=>({url:location.href,cid:document.body.dataset.conversationId,value:document.getElementById('composer').value,start:document.getElementById('composer').selectionStart,end:document.getElementById('composer').selectionEnd,history:document.getElementById('history').innerHTML,materials:document.getElementById('material-list').innerHTML}));
   const materialsBefore=await context.request.get(origin+'/api/assistant/conversations/'+cid+'/materials').then(r=>r.json());
   await windowOfModeSwitch('settled-mode-round-trip',async()=>{await mode('chat');await mode('workbench');await mode('chat');});
   const after=await p.evaluate(()=>({url:location.href,cid:document.body.dataset.conversationId,value:document.getElementById('composer').value,start:document.getElementById('composer').selectionStart,end:document.getElementById('composer').selectionEnd,history:document.getElementById('history').innerHTML,materials:document.getElementById('material-list').innerHTML,sameComposer:window.__dualView.composer===document.getElementById('composer'),sameHistory:window.__dualView.history===document.getElementById('history')}));
   assert.equal(after.sameComposer,true);assert.equal(after.sameHistory,true);delete after.sameComposer;delete after.sameHistory;assert.deepEqual(after,snapshot);assert.equal(original,after.value);
   const materialsAfter=await context.request.get(origin+'/api/assistant/conversations/'+cid+'/materials').then(r=>r.json());assert.deepEqual(materialsAfter,materialsBefore);
  });
  await check('actual local autosave pending during mode switch saves the same content',async()=>{
   await mode('workbench');await settle();const original=await p.locator('#composer').inputValue();restoreDraft=original;
   let intercepted,release;const received=new Promise(resolve=>intercepted=resolve),hold=new Promise(resolve=>release=resolve);
   const endpoint=origin+'/api/assistant/conversations/'+cid+'/draft';let payload;
   await p.route(endpoint,async route=>{if(route.request().method()!=='PUT')return route.fallback();payload=route.request().postDataJSON();intercepted();await hold;return route.continue();});
   const changed=original+'\n双视图验收：此段仅为虚构本机草稿。';await p.locator('#composer').fill(changed);await Promise.race([received,pause(12000).then(()=>{release();throw new Error('expected draft PUT was not intercepted in 12 seconds');})]);
   try{assert.match(await p.locator('#save-status').innerText(),/正在保存/);const start=requestLog.length;await mode('chat');await mode('workbench');assert.equal(await p.locator('#composer').inputValue(),changed);assert.equal(requestLog.slice(start).filter(r=>r.method!=='GET').length,0);}
   finally{release();}
   await p.waitForFunction(()=>document.getElementById('save-status').textContent.includes('草稿已保存到本机'));await p.unroute(endpoint);
   assert.equal(payload.content,changed);const data=await context.request.get(origin+'/api/assistant/conversations/'+cid).then(r=>r.json());assert.equal(data.draft_input,changed);
   await p.locator('#composer').fill(original);await p.locator('#save-draft').click();await p.waitForFunction(()=>document.getElementById('save-status').textContent.includes('草稿已保存到本机'));restoreDraft=null;
  });
  await check('responsive chat has no horizontal overflow and a reachable composer at four widths',async()=>{
   await mode('chat');
   for(const [width,height]of[[1440,900],[1224,785],[768,900],[390,844]]){
    await p.setViewportSize({width,height});await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const geometry=await p.evaluate(()=>{const t=document.getElementById('conversation-thread'),c=document.getElementById('composer'),f=document.getElementById('composer-form'),r=e=>{const b=e.getBoundingClientRect();return{x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom}};return{viewport:innerWidth,pageWidth:document.documentElement.scrollWidth,pageHeight:document.documentElement.scrollHeight,viewportHeight:innerHeight,composer:r(c),form:r(f),thread:r(t),threadOverflow:getComputedStyle(t).overflowY,overflowElements:[...document.querySelectorAll('body *')].filter(e=>{const b=e.getBoundingClientRect();return getComputedStyle(e).display!=='none'&&b.width>0&&b.right>innerWidth+1}).slice(0,12).map(e=>({id:e.id,className:String(e.className),right:e.getBoundingClientRect().right}))};});
    report.geometry.push({width,height,...geometry});assert.ok(geometry.pageWidth<=width+1,'horizontal overflow '+width);assert.ok(geometry.composer.y>=0&&geometry.composer.bottom<=height+1,'composer on screen '+width);assert.ok(geometry.thread.bottom<=geometry.form.y+2,'thread does not lie underneath composer '+width);assert.ok(['auto','scroll'].includes(geometry.threadOverflow),'thread scroll container '+width);
    await p.locator('#composer').focus();assert.equal(await p.evaluate(()=>document.activeElement.id),'composer');
    await p.screenshot({path:path.join(directory,'chat-'+width+'.png'),fullPage:false});
   }
   await p.setViewportSize({width:1440,height:900});
  });
  await check('390px at reading size 20 keeps tools and a scrollable worksheet usable; many materials scroll within compose (DOM replay)',async()=>{
   await mode('chat');await p.setViewportSize({width:390,height:844});await p.locator('#body-size').selectOption('20');await tools();
   const menu=await p.locator('.workspace-tabs').boundingBox();report.narrowMenu=menu;const menuVisible=menu.x>=0&&menu.x+menu.width<=391&&menu.y+menu.height<=845;await p.screenshot({path:path.join(directory,'chat-390-size20-tools.png')});
   await p.locator('#show-worksheet').click();await p.locator('#worksheet-panel').waitFor({state:'visible'});const sheet=await p.locator('#worksheet-panel').evaluate(e=>{e.scrollTop=e.scrollHeight;return{scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,scrollTop:e.scrollTop,overflow:getComputedStyle(e).overflowY};});report.narrowWorksheet=sheet;assert.ok(sheet.scrollHeight>sheet.clientHeight&&sheet.scrollTop>0&&['auto','scroll'].includes(sheet.overflow),'worksheet scrolls independently');await p.locator('#close-chat-workarea').click();await p.waitForFunction(()=>!document.getElementById('chat-workarea').classList.contains('is-open'));
   const added=await p.evaluate(()=>{const h=document.getElementById('material-list'),source=h.querySelector('.material-row');for(let i=0;i<10;i++){const row=source.cloneNode(true);row.dataset.dualMaterialReplay='true';h.append(row);}return 10;});report.replays.push({name:'many materials',method:'DOM-only duplicate real synthetic local material rows; no upload/selection mutation',added});
   const compose=await p.locator('.compose-section').evaluate(e=>({scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,overflow:getComputedStyle(e).overflowY}));report.manyMaterialsCompose=compose;assert.ok(['auto','scroll'].includes(compose.overflow),'compose supports overflow scrolling');const materialScroll=await p.locator('#material-list').evaluate(e=>({scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,overflow:getComputedStyle(e).overflowY}));report.manyMaterialsList=materialScroll;assert.ok((materialScroll.scrollHeight>materialScroll.clientHeight&&['auto','scroll'].includes(materialScroll.overflow))||compose.scrollHeight>compose.clientHeight,'material list or compose owns material overflow');await p.locator('#composer').scrollIntoViewIfNeeded();await p.locator('#composer').focus();const input=await p.locator('#composer').boundingBox();assert.ok(input.y>=0&&input.y+input.height<=845,'input reachable after many materials');assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.screenshot({path:path.join(directory,'chat-390-size20-many-materials.png')});
   await p.evaluate(()=>document.querySelectorAll('[data-dual-material-replay]').forEach(e=>e.remove()));await p.locator('#body-size').selectOption('16');await p.setViewportSize({width:1440,height:900});assert.ok(menuVisible,'narrow tools menu remains in viewport');
  });
  await check('long-history manual scroll survives mode round trip (DOM replay only if fixture is short)',async()=>{
   await mode('chat');const added=await p.evaluate(()=>{const t=document.getElementById('conversation-thread');if(t.scrollHeight>t.clientHeight+500)return 0;const h=document.getElementById('history'),source=h.querySelector('article');for(let i=0;i<18;i++){const a=source.cloneNode(true);a.dataset.dualViewReplay='true';a.removeAttribute('id');a.querySelectorAll('[id]').forEach(e=>e.removeAttribute('id'));h.append(a);}return 18;});
   if(added)report.replays.push({name:'long history',method:'DOM-only repeated synthetic saved history articles',added});
   await p.evaluate(()=>{const t=document.getElementById('conversation-thread');t.scrollTop=Math.min(280,t.scrollHeight-t.clientHeight-100);});
   const before=await p.locator('#conversation-thread').evaluate(e=>e.scrollTop);assert.ok(before>0,'scroll fixture is long enough');
   await windowOfModeSwitch('manual-scroll-mode-round-trip',async()=>{await mode('workbench');await mode('chat');});const after=await p.locator('#conversation-thread').evaluate(e=>e.scrollTop);assert.ok(Math.abs(after-before)<=2,'manual scroll retained: '+before+' => '+after);
   await p.evaluate(()=>document.querySelectorAll('[data-dual-view-replay],[data-dual-material-replay]').forEach(e=>e.remove()));
  });
  await check('chat tools open all three real worksheet editors and return focus on close/Escape',async()=>{
   for(const [trigger,panel,input]of[['show-worksheet','worksheet-panel','worksheet-notes'],['show-evidence','evidence-panel','evidence-content'],['show-followups','followup-panel','followup-title']]){
    await chatAction(trigger);await p.locator('#'+panel).waitFor({state:'visible'});await p.waitForFunction(id=>!document.getElementById(id).disabled,input);await p.locator('#'+input).focus();assert.equal(await p.evaluate(()=>document.activeElement.id),input);
    await p.locator('#close-chat-workarea').click();await p.waitForFunction(()=>!document.getElementById('chat-workarea').classList.contains('is-open'));assert.equal(await p.evaluate(()=>document.activeElement.id),'conversation-tools-summary');
    await tools();await p.locator('#'+trigger).click();await p.locator('#'+panel).waitFor({state:'visible'});await p.keyboard.press('Escape');await p.waitForFunction(()=>!document.getElementById('chat-workarea').classList.contains('is-open'));assert.equal(await p.evaluate(()=>document.activeElement.id),'conversation-tools-summary');
   }
  });
  await check('unsaved reception worksheet survives mode changes and keeps the original navigation guard',async()=>{
   await chatAction('show-worksheet');await p.waitForFunction(()=>!document.getElementById('worksheet-notes').disabled);const original=await p.locator('#worksheet-notes').inputValue(),changed=original+'\n双视图验收：未保存编辑应保留。';
   await p.locator('#worksheet-notes').fill(changed);await mode('workbench');await mode('chat');await tools();await p.locator('#show-worksheet').click();await p.locator('#worksheet-notes').waitFor({state:'visible'});assert.equal(await p.locator('#worksheet-notes').inputValue(),changed);
   await p.locator('#close-chat-workarea').click();const url=p.url();await p.locator('#new-conversation').click();assert.equal(p.url(),url);assert.match(await p.locator('#notice').innerText(),/保存|清空/);
   await tools();await p.locator('#show-worksheet').click();await p.locator('#worksheet-notes').fill(original);await p.waitForFunction(()=>document.getElementById('worksheet-save').disabled);await p.locator('#close-chat-workarea').click();
  });
  await check('chat profile, outputs and material original retain usable drawers and focus restoration',async()=>{
   for(const [trigger,panel,close]of[['show-profile','profile-preview','close-profile-preview'],['show-outputs','output-panel','close-outputs']]){
    await chatAction(trigger);await p.locator('#'+panel).waitFor({state:'visible'});await p.locator('#'+close).click();await p.locator('#'+panel).waitFor({state:'hidden'});await p.waitForFunction(()=>document.activeElement.id==='conversation-tools-summary',null,{timeout:2500});
    await tools();await p.locator('#'+trigger).click();await p.locator('#'+panel).waitFor({state:'visible'});await p.keyboard.press('Escape');await p.locator('#'+panel).waitFor({state:'hidden'});await p.waitForFunction(()=>document.activeElement.id==='conversation-tools-summary',null,{timeout:2500});
   }
   const material=p.locator('#material-list').getByRole('button',{name:'核对原文',exact:true}).first();assert.ok(await material.count(),'fixture must include one actual local material');await material.click();await p.locator('#material-preview').waitFor({state:'visible'});await p.locator('#close-material-preview').click();await p.locator('#material-preview').waitFor({state:'hidden'});await p.waitForFunction(()=>['add-material','conversation-tools-summary'].includes(document.activeElement.id),null,{timeout:2500});await material.click();await p.locator('#material-preview').waitFor({state:'visible'});await p.keyboard.press('Escape');await p.locator('#material-preview').waitFor({state:'hidden'});await p.waitForFunction(()=>['add-material','conversation-tools-summary'].includes(document.activeElement.id),null,{timeout:2500});
  });
  await check('actual Word client export excludes internal notes, while internal export retains them',async()=>{
   await chatAction('show-outputs');await p.locator('#output-source option').nth(1).waitFor({state:'attached'});await p.locator('#output-source').selectOption('0');
   const saved={};for(const audience of ['client','internal']){
    await p.locator('#output-audience').selectOption(audience);await p.locator('#output-preview').click();await p.locator('#output-result').waitFor({state:'visible'});const text=await p.locator('#output-text').innerText();
    const download=await Promise.all([p.waitForEvent('download'),p.locator('#output-download').click()]).then(a=>a[0]);const file=path.join(directory,audience+'-export.docx');await download.saveAs(file);const docx=parseDocx(file);assert.ok(fs.statSync(file).size>1000);saved[audience]={preview:text,docx,file};
   }
   assert.match(saved.client.preview,/您好/);assert.doesNotMatch(saved.client.docx,/一、客户诉求|二、我方立场/);assert.match(saved.internal.docx,/一、客户诉求|二、我方立场/);report.exports=saved;
   await p.locator('#close-outputs').click();
  });
  await check('generating indicator and send-disabled state survive toggles (explicit HTTP replay, no model)',async()=>{
   const url=origin+'/api/assistant/conversations/'+cid;let replayedRun;
   await p.route(url,async route=>{if(route.request().method()!=='GET')return route.fallback();const response=await route.fetch(),body=await response.json();assert.ok(body.latest_run,'fixture has real saved local run metadata');body.latest_run={...body.latest_run,state:'generating'};replayedRun=body.latest_run.id;return route.fulfill({response,json:body});});
   await p.route(url+'/generation-capability',async route=>{const response=await route.fetch(),body=await response.json();body.state='busy';return route.fulfill({response,json:body});});
   await p.reload();await p.locator('#history article').first().waitFor();await p.locator('#run-status').filter({hasText:'正在生成'}).waitFor();await settle();const before=requestLog.length;await mode('chat');await mode('workbench');await mode('chat');assert.match(await p.locator('#run-status').textContent(),/正在生成/);assert.equal(await p.locator('#send').isDisabled(),true);assert.equal(requestLog.slice(before).filter(r=>r.method!=='GET').length,0);
   report.replays.push({name:'generating state',method:'GET conversation actual JSON; latest_run.state only replaced with generating; GET capability state replaced with busy',run_id:replayedRun,model_calls:0});await p.unroute(url);await p.unroute(url+'/generation-capability');
  });
  await check('readonly still disables composer, send and draft save in both modes (explicit HTML replay)',async()=>{
   const c=await createContext();await c.route(origin+'/assistant/'+cid,async route=>{const response=await route.fetch(),html=await response.text();assert.match(html,/data-readonly="false"/);return route.fulfill({response,body:html.replace('data-readonly="false"','data-readonly="true"')});});
   const previous=p;p=await c.newPage();p.setDefaultTimeout(10000);p.on('pageerror',error=>report.page_errors.push(error.message));await p.goto(origin+'/assistant/'+cid);await p.locator('#history article').first().waitFor();await settle();
   for(const value of ['workbench','chat']){await mode(value);assert.equal(await p.locator('#composer').isDisabled(),true);assert.equal(await p.locator('#save-draft').isDisabled(),true);assert.equal(await p.locator('#send').isDisabled(),true);}
   report.replays.push({name:'readonly controls',method:'isolated HTML body data-readonly=true replay; normal saved data, no real restore/backup security acceptance'});await p.close();p=previous;
  });
 }catch(error){report.fatal=String(error);}
 finally{
  // A failed assertion must not leave the fake shared draft changed.
  if(restoreDraft!==null&&p&&!p.isClosed())try{await p.unrouteAll({behavior:'ignoreErrors'});await p.reload();await p.locator('#composer').waitFor();await p.locator('#composer').fill(restoreDraft);await p.locator('#save-draft').click();await p.waitForFunction(()=>document.getElementById('save-status').textContent.includes('草稿已保存到本机'));}catch(error){report.restore_error=String(error);}
  report.pass=!report.fatal&&report.checks.every(c=>c.pass)&&!report.page_errors.length&&!report.external_requests.length&&!report.forbidden_model_requests.length;
  report.finished=new Date().toISOString();fs.writeFileSync(path.join(directory,'dual-view-checks.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report));if(!report.pass)process.exitCode=1;
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
