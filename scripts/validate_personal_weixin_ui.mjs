// Fictional component acceptance: no Weixin transport, model or credentials.
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE);
const output=path.resolve(process.argv[2]);mkdirSync(output,{recursive:true});
const fromIndex=process.argv.includes('--index');
const read=name=>fromIndex?execFileSync('git',['show',':'+name]):readFileSync(name);
const template=read('src/cn_contract/web/templates/assistant.html').toString();
const panel=template.slice(template.indexOf('      <details id="personal-weixin-panel"'),template.indexOf('      <section class="history-section"'));
const css=read('src/cn_contract/web/static/assistant.css');
const files=new Map([
  ['/assistant.css',css],
  ['/assistant-weixin-personal.css',read('src/cn_contract/web/static/assistant-weixin-personal.css')],
  ['/assistant-weixin-personal.mjs',read('src/cn_contract/web/static/assistant-weixin-personal.mjs')],
]);
const html=`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>虚构微信连接界面验收</title>
<link rel="stylesheet" href="/assistant.css"><link rel="stylesheet" href="/assistant-weixin-personal.css"><main class="assistant-main"><div class="conversation-surface"><h1>虚构合同审查</h1>${panel}<label for="composer">未发送文字</label><textarea id="composer">保留本地虚构草稿</textarea></div></main>
<script type="module">import {bindPersonalWeixin} from '/assistant-weixin-personal.mjs';
const cid='11111111-2222-4333-8444-555555555555';
window.fixture={status:{state:'waiting_scan',conversation_id:cid,automatic:true,notice:'请用本人微信扫码，收件固定到当前聊天。',qr_ready:true},calls:[]};
const controller={state:{id:cid,status:'saved',loading:false,view:{},text:'保留本地虚构草稿',dirty:true}};
const bridge={personalWeixinStatus:async()=>({ok:true,connection:window.fixture.status}),personalWeixinStart:async()=>({ok:true}),
 personalWeixinDisable:async()=>{fixture.status=null;return {ok:true};},personalWeixinVerify:async code=>{fixture.calls.push(code);return {ok:true};}};
window.ui=bindPersonalWeixin({controller,bridge,onIncoming:async()=>{},setTimer:()=>1,clearTimer:()=>{}});ui.state(controller.state);document.getElementById('personal-weixin-panel').open=true;await ui.refresh();window.ready=true;</script></html>`;
files.set('/',Buffer.from(html));
const qr=execFileSync(path.resolve('.venv/Scripts/python.exe'),['-c',"import qrcode;from qrcode.image.svg import SvgPathImage;import sys;sys.stdout.buffer.write(qrcode.make('https://ilinkai.weixin.qq.com/qr/fiction',image_factory=SvgPathImage).to_string())"]);
files.set('/api/assistant/conversations/11111111-2222-4333-8444-555555555555/personal-weixin/qr.svg',qr);
const server=createServer((req,res)=>{
  const content=files.get(req.url);if(!content){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',req.url.endsWith('.css')?'text/css':req.url.endsWith('.mjs')?'text/javascript':req.url.endsWith('.svg')?'image/svg+xml':'text/html; charset=utf-8');res.end(content);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),page=await browser.newPage(),errors=[],external=[],checks=[];
page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:'))external.push(r.url());});
try{
  await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>window.ready);
  for(const width of [1280,640,360]){
    await page.setViewportSize({width,height:900});await page.locator('#personal-weixin-refresh').focus();
    const dimensions=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,
      qrLoaded:document.getElementById('personal-weixin-qr').naturalWidth>0,focus:document.activeElement.id}));
    if(dimensions.scroll>dimensions.client||!dimensions.qrLoaded||dimensions.focus!=='personal-weixin-refresh')throw new Error(JSON.stringify(dimensions));
    await page.screenshot({path:path.join(output,'waiting-scan-'+width+'.png'),fullPage:true});checks.push({width,...dimensions});
  }
  await page.evaluate(async()=>{fixture.status={...fixture.status,state:'need_verifycode',qr_ready:false};await ui.refresh();});
  await page.locator('#personal-weixin-code').fill('001234');await page.locator('#personal-weixin-code').press('Enter');
  await page.waitForFunction(()=>fixture.calls.length===1);
  if(await page.locator('#composer').inputValue()!=='保留本地虚构草稿')throw new Error('draft lost');
  if(await page.evaluate(()=>fixture.calls[0])!=='001234')throw new Error('verification altered');
  await page.screenshot({path:path.join(output,'verification-360.png'),fullPage:true});
  if(errors.length||external.length)throw new Error(JSON.stringify({errors,external}));
  const report={status:'PASS',source:fromIndex?'git-index':'working-tree',checks,keyboard_verify:true,dirty_composer_preserved:true,page_errors:errors,external_requests:external,live_weixin:false,live_model:false};
  writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
