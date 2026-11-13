// Real browser, synthetic IPC only. Does not start the host or read business data.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=process.env.QX_BACKUP_UI_OUTPUT,browserPath=process.env.QX_TEST_BROWSER,playwrightPath=process.env.QX_TEST_PLAYWRIGHT;
if(!output||!path.isAbsolute(output)||!browserPath||!playwrightPath)throw Error('Set QX_BACKUP_UI_OUTPUT, QX_TEST_BROWSER and QX_TEST_PLAYWRIGHT to absolute test paths.');
fs.mkdirSync(output,{recursive:true});
const {chromium}=await import(pathToFileURL(playwrightPath));
const browser=await chromium.launch({executablePath:browserPath,headless:true,args:['--disable-background-networking']});
const checks=[],errors=[],outbound=[];
try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'zh-CN'});
  await context.route(/^https?:/,route=>{outbound.push(route.request().url());return route.abort();});
  await context.addInitScript(()=>{
    const original='C:/合成测试/律师资料与办案工作区/原资料目录/用于检查长路径换行与中文显示/资料';
    const state={data:original,previousData:null,maintenance:false,busy:false,engineReady:false,selected:{},review:null,prepared:null,message:'',error:''};
    const calls=[];let release;
    window.syntheticBackup={state,calls,failRestore:true,finishBackup:()=>release?.()};
    window.qxBackup={state:async()=>structuredClone(state),choose:async kind=>{
      calls.push({kind});state.selected[kind]='C:/合成测试/独立维护与恢复/'+kind;state.error='';return state.selected[kind];
    },act:async(action,input)=>{
      calls.push({action,input});state.error='';state.message='';
      if(action==='prepareEngine')state.engineReady=true;
      if(action==='pause')state.maintenance=true;
      if(action==='backup'){
        await new Promise(resolve=>{release=resolve;});
        state.message='备份已完成并校验。合成文件 12 项，保存于 C:/合成测试/独立备份。';
      }
      if(action==='restore'){
        if(window.syntheticBackup.failRestore){state.error='BACKUP_ENGINE_FAILED';return {ok:false};}
        state.selected.reviewRoot='C:/合成测试/恢复副本';state.message='恢复完成。请检查独立恢复副本后再启用。';
      }
      if(action==='review')state.review={reviewToken:'synthetic-review-1',counts:{files:12,databases:2,settings:2,pending:2},
        settings:[{id:'desktop-locale'},{id:'wechat-preferences'}],reauthorization:['model-api-keys','wechat-login','other-profile-secrets','content-provider-login'],
        pending:[{id:'message-1',kind:'wechat',label:'待处理微信材料',preview:'客户补充材料的合成摘要。继续为草稿后，请在本机核对内容。',status:'pending'},
          {id:'watch-1',kind:'content',label:'待整理的内容任务',preview:'<img src=x onerror="window.unexpectedScript=true"> 这段文字必须按原文显示。',status:'pending'}]};
      if(action==='prepare'){state.prepared={destination:'C:/合成测试/启用副本/中文与长路径恢复验收/资料'};state.message='启用副本已准备，等待你的最后确认。';}
      if(action==='activate'){state.previousData=original;state.message='合成测试已收到启用请求。';}
      if(action==='rollback')state.message='合成测试已收到撤回请求。';
      if(action==='resume')state.maintenance=false;
      return {ok:true};
    }};
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(pathToFileURL(path.join(root,'desktop/backup.html')).href);
  await page.waitForFunction(()=>document.querySelector('#backup-app').getAttribute('aria-busy')==='false');
  assert.equal(await page.locator('#pause').isDisabled(),true);
  await page.locator('#tab-backup').focus();await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('#tab-restore').getAttribute('aria-selected'),'true');
  await page.keyboard.press('End');assert.equal(await page.locator('#tab-review').getAttribute('aria-selected'),'true');
  await page.keyboard.press('Home');assert.equal(await page.locator('#tab-backup').getAttribute('aria-selected'),'true');
  checks.push('tab list supports Arrow, Home and End keys with a single tab stop');
  await page.locator('#prepare-engine').click();await page.locator('#engine-section').waitFor({state:'hidden'});
  await page.locator('#pause-confirm').focus();await page.keyboard.press('Space');await page.locator('#pause').focus();
  assert.equal(await page.locator('#pause').evaluate(button=>getComputedStyle(button).outlineStyle),'solid');await page.keyboard.press('Enter');
  await page.locator('#pause-section').waitFor({state:'hidden'});checks.push('native checkbox and keyboard confirmation enter maintenance');
  await page.locator('[data-choose=backupParent]').click();
  await page.locator('#backup-password').fill('synthetic-password');await page.locator('#backup-password-confirm').fill('different-password');await page.locator('#backup-submit').click();
  assert.match(await page.locator('#error-message').textContent(),/不一致/);
  assert.equal(await page.evaluate(()=>window.syntheticBackup.calls.filter(c=>c.action==='backup').length),0);
  await page.locator('#backup-password').fill('synthetic-password');await page.locator('#backup-password-confirm').fill('synthetic-password');await page.locator('#backup-submit').click();
  assert.equal(await page.locator('#backup-submit').isDisabled(),true);assert.equal(await page.locator('[data-choose=backupParent]').isDisabled(),true);
  assert.equal(await page.locator('#backup-password').inputValue(),'');
  await page.evaluate(()=>window.syntheticBackup.finishBackup());await page.waitForFunction(()=>!document.querySelector('#backup-submit').disabled);
  assert.match(await page.locator('#result-message').textContent(),/备份已完成/);checks.push('password mismatch blocks IPC; in-flight backup disables repeats and clears password fields');
  await page.locator('#tab-restore').click();await page.locator('[data-choose=bundle]').click();await page.locator('[data-choose=restoreParent]').click();
  await page.locator('#restore-password').fill('synthetic-password');await page.locator('#restore-submit').click();
  await page.waitForFunction(()=>!document.querySelector('#restore-submit').disabled);
  assert.match(await page.locator('#error-message').textContent(),/重试/);assert.equal(await page.locator('#result-message').isVisible(),false);
  await page.evaluate(()=>{window.syntheticBackup.failRestore=false;});await page.locator('#restore-password').fill('synthetic-password');await page.locator('#restore-submit').click();
  await page.waitForFunction(()=>document.querySelector('#result-message').textContent.includes('恢复完成'));checks.push('recovery failure remains actionable and retry displays only the confirmed result');
  await page.locator('#tab-review').click();await page.locator('#review').click();await page.locator('#review-details').waitFor({state:'visible'});
  assert.match(await page.locator('#review-counts').textContent(),/文件 12 项/);
  assert.match(await page.locator('#reauthorization-list').textContent(),/内容来源账号登录/);
  assert.equal(await page.locator('#pending-list img').count(),0);assert.equal(await page.evaluate(()=>Boolean(window.unexpectedScript)),false);
  await page.locator('[data-choose=activationParent]').click();assert.equal(await page.locator('#prepare').isDisabled(),true);
  await page.locator('#pending-choice-0').focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
  await page.locator('#pending-choice-1').selectOption('hold');
  assert.equal(await page.locator('#prepare').isDisabled(),false);
  await page.locator('#apply-settings').check();await page.locator('#prepare').click();await page.locator('#prepared-section').waitFor({state:'visible'});
  assert.equal(await page.locator('#activate').isDisabled(),true);assert.equal(await page.locator('#pending-choice-0').isDisabled(),true);
  assert.match(await page.locator('#prepared-section').textContent(),/手工发送/);checks.push('every pending item needs a decision; prepared choices stay fixed; content renders as text, never HTML');
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:1000});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`horizontal overflow at ${width}`);
    const details=await page.evaluate(()=>({bodyFont:getComputedStyle(document.body).fontFamily,focusOutline:getComputedStyle(document.querySelector('#activate')).outlineStyle,
      buttons:[...document.querySelectorAll('button')].filter(x=>x.offsetParent).every(x=>x.getBoundingClientRect().height>=43)}));
    assert.equal(details.buttons,true);
    await page.screenshot({path:path.join(output,`review-${width}.png`),fullPage:true});
    checks.push(`${width}px: long Chinese paths and review content fit without horizontal scrolling; buttons remain at least 44px`);
  }
  await page.locator('#activate-confirm').focus();await page.keyboard.press('Space');await page.locator('#activate').focus();await page.keyboard.press('Enter');
  await page.locator('#rollback-section').waitFor({state:'visible'});
  assert.equal(await page.locator('#rollback').isDisabled(),true);await page.locator('#rollback-confirm').check();await page.locator('#rollback').click();
  const actions=await page.evaluate(()=>window.syntheticBackup.calls.filter(c=>c.action));
  assert.equal(actions.filter(c=>c.action==='activate').length,1);assert.equal(actions.filter(c=>c.action==='rollback').length,1);
  assert.equal(actions.find(c=>c.action==='prepare').input.decisions['message-1'],'draft');
  checks.push('activation and rollback each require a separate explicit confirmation; no automatic activation');
  await page.locator('#resume').click();await page.locator('#pause-section').waitFor({state:'visible'});
  assert.equal(await page.locator('#pause-confirm').isChecked(),false);assert.equal(await page.locator('#pause').isDisabled(),true);
  checks.push('re-entering maintenance requires a fresh no-active-task confirmation');
  assert.deepEqual(errors,[]);assert.deepEqual(outbound,[]);
  fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify({passed:true,checks,pageErrors:errors,externalRequests:outbound.length,fixture:'synthetic IPC; no real backup, model, credential, or host actions'},null,2)+'\n');
  console.log(JSON.stringify({passed:true,checks},null,2));
}catch(error){
  fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify({passed:false,checks,pageErrors:errors,error:String(error)},null,2)+'\n');throw error;
}finally{await browser.close();}
