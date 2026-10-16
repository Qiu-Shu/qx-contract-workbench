const { _electron } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const repo = path.resolve(__dirname,'../..'), output=path.resolve(process.argv[2]);
const executable=process.argv[3]||path.join(repo,'desktop/node_modules/electron/dist/electron.exe');
const data=path.join(output,'中文 恢复资料'), library=path.join(output,'合成库');
fs.mkdirSync(library,{recursive:true});fs.mkdirSync(data,{recursive:true});
for(const file of ['catalog.sqlite','current.json'])fs.writeFileSync(path.join(library,file),'{}');
const launch=()=>_electron.launch({executablePath:executable,args:process.argv[3]?[]:[path.join(repo,'desktop')],
  cwd:repo,env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:60000});
let application;const report={checks:[]};
(async()=>{try {
 application=await launch();let page=await application.firstWindow();await page.locator('#setup').waitFor({state:'visible'});
 const obstruct=path.join(data,'desktop-settings.json.tmp');fs.mkdirSync(obstruct);
 await application.evaluate(({dialog},selected)=>{
   dialog.showOpenDialog=async()=>({canceled:false,filePaths:[selected]});
   dialog.showMessageBox=async (_win,options)=>{dialog.__testDialog=options.message;return {response:0};};
 },library);
 assert.deepEqual(await page.evaluate(()=>window.desktopSetup.chooseLibrary()),{ok:false});
 assert.equal((await page.evaluate(()=>window.desktopSetup.state())).library,'');
 assert.match(await application.evaluate(({dialog})=>dialog.__testDialog),/原设置已保留/);
 assert.equal(fs.existsSync(path.join(data,'desktop-settings.json')),false);
 report.checks.push('failed-settings-write-atomic-and-redacted');fs.rmdirSync(obstruct);
 // Make a real account before simulating the disappearance of an optional library.
 await page.locator('#username').fill('恢复验收');await page.locator('#password').fill('fiction123');await page.locator('#confirm').fill('fiction123');
 await page.locator('#setup button[type=submit]').click();await page.waitForURL(/\/login$/,{timeout:45000});
 await application.close();application=null;
 fs.writeFileSync(path.join(data,'desktop-settings.json'),JSON.stringify({library_root:path.join(output,'missing-library')}));
 application=await launch();page=await application.firstWindow();await page.locator('#retry').waitFor({state:'visible',timeout:45000});
 assert.equal(fs.existsSync(path.join(output,'missing-library')),false);
 await application.evaluate(({Menu})=>Menu.getApplicationMenu().items[0].submenu.items.find(x=>x.label==='断开资料库连接').click());
 await page.waitForURL(/\/login$/,{timeout:45000});
 assert.deepEqual(JSON.parse(fs.readFileSync(path.join(data,'desktop-settings.json'),'utf8')),{});
 report.checks.push('missing-library-no-write','disconnect-restores-account-login');report.status='PASS';
 }catch(error){report.status='FAIL';report.error=error.stack;throw error;}
 finally{if(application)await application.close();fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})().catch(error=>{console.error(error);process.exitCode=1;});
