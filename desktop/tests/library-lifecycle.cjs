// Read-only connection to the already accepted local library; isolated case data.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const output=path.resolve(process.argv[2]),exe=path.resolve(process.argv[3]),library=path.resolve(process.argv[4]);
const data=path.join(output,'中文 用户资料');
const currentBefore=fs.readFileSync(path.join(library,'current.json'));
const launch=()=>_electron.launch({executablePath:exe,args:[],env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
let application,page;const report={checks:[]};
async function login(){await page.waitForURL(/\/login$/,{timeout:60000});await page.locator('[name=username]').fill('桌面合成律师');await page.locator('[name=password]').fill('fiction123');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL(/127\.0\.0\.1:\d+\/$/);}
async function api(url,body){return page.evaluate(async({url,body})=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('qx_csrf='))?.slice(8)||'');const r=await fetch(url,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},body:body?JSON.stringify(body):undefined});if(!r.ok)throw new Error('HTTP '+r.status);return r.json();},{url,body});}
async function childPid(){const mainPid=await application.evaluate(()=>process.pid);return Number(execFileSync('powershell.exe',['-NoProfile','-Command',`(Get-CimInstance Win32_Process -Filter "Name='qx-backend.exe' AND ParentProcessId=${mainPid}").ProcessId`],{encoding:'utf8',windowsHide:true}).trim());}
(async()=>{try{
 application=await launch();page=await application.firstWindow();await login();
 await application.evaluate(({Menu,dialog},selected)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[selected]});return Menu.getApplicationMenu().items[0].submenu.items.find(x=>x.label==='连接法律资料库…').click();},library);
 await login();await page.getByRole('link',{name:'法律资料库',exact:true}).click();
 const status=await api('/api/library/status');assert.equal(status.state,'ready');report.generation=status.generation_id;report.coverage=status.coverage;
 await page.locator('#kind').selectOption('law_markdown');await page.locator('#province').fill('吉林省');
 await page.locator('#search-button').click();await page.locator('#results button').first().waitFor({timeout:60000});
 await page.locator('#results button').first().click();await page.locator('#original-content').waitFor({state:'visible'});
 assert.ok((await page.locator('#original-text').innerText()).length>20);
 const cases=await api('/api/library/search',{text:'',kind:'case_csv',province:'吉林省',limit:5});assert.ok(cases.hits.length>0);
 report.caseHits=cases.hits.length;report.checks.push('installed-library-connection','full-generation-ready','jilin-law-ui-original','jilin-case-search');
 report.electronMetrics=await application.evaluate(({app})=>app.getAppMetrics().map(p=>({type:p.type,pid:p.pid,workingSetKB:p.memory.workingSetSize})));
 const child=await childPid();assert.ok(child>0);const oldOrigin=new URL(page.url()).origin;
 report.backendWorkingSetBytes=Number(execFileSync('powershell.exe',['-NoProfile','-Command',`(Get-Process -Id ${child}).WorkingSet64`],{encoding:'utf8',windowsHide:true}).trim());
 // Stop only this owned backend; the window must offer recovery.
 process.kill(child);await page.locator('#retry').waitFor({state:'visible',timeout:30000});
 await page.locator('#retry').click();await login();assert.ok((await api('/api/matters')).length>0);
 report.checks.push('backend-crash-visible','backend-restart-keeps-case');
 const finalChild=await childPid();assert.ok(finalChild>0);
 const mainPid=await application.evaluate(()=>process.pid),launcher=application.process();
 process.kill(mainPid);application=null;
 for(let i=0;i<40;i++){try{process.kill(finalChild,0);}catch{break;}await new Promise(resolve=>setTimeout(resolve,500));}
 assert.throws(()=>process.kill(finalChild,0));report.checks.push('parent-crash-stops-owned-backend');
 if(launcher.exitCode===null)launcher.kill();
 assert.deepEqual(fs.readFileSync(path.join(library,'current.json')),currentBefore);report.checks.push('published-library-pointer-unchanged');report.status='PASS';
}catch(error){report.status='FAIL';report.error=error.stack;throw error;}
finally{if(application)await application.close();fs.writeFileSync(path.join(output,'library-lifecycle.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,checks:report.checks.length}));}
})().catch(error=>{console.error(error);process.exitCode=1;});
