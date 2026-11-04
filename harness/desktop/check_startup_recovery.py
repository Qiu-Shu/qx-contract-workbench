"""Real Electron startup failure must retain the saved API key and recover without setup."""
import json,os,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'.local/recovery-checks';out.mkdir(exist_ok=True)
fixture=out/('electron-'+str(int(time.time())));fixture.mkdir()
payload=fixture/'payload';payload.mkdir();data=fixture/'data'
staged=ROOT/'.local/package-updates-0.2.3/workbench'
shutil.copytree(staged/'workspace-seed',payload/'workspace-seed')
(payload/'config').mkdir()
for name in ['portable.json','profile-package.json','profile-cordis.yml','contract-0.2.0-defaults.json']:
    shutil.copy2(staged/'config'/name,payload/'config'/name)
(payload/'runtime').mkdir();os.link(staged/'runtime/node.exe',payload/'runtime/node.exe')
(payload/'desktop-runner').mkdir()
for name in ['installed-host.cjs','installed-runtime.cjs','installed-migrations.cjs','host-recovery.cjs']:
    shutil.copy2(ROOT/'desktop'/name,payload/'desktop-runner'/name)
binpath=payload/'node_modules/@deepseek-ai/dsh/lib';binpath.mkdir(parents=True)
(binpath/'bin.js').write_text("""
const fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const port=Number(process.argv[process.argv.indexOf('--port')+1]);
const html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>测试后台</title><h1>隔离恢复测试</h1><textarea aria-label="未发送内容"></textarea></html>';
http.createServer((req,res)=>{
  if(req.method==='POST')fs.appendFileSync(path.join(process.env.QX_INSTALL_DATA,'unexpected-posts.txt'),req.url+'\\n');
  res.setHeader('Content-Type',req.url==='/qx-wechat/state'?'application/json':'text/html; charset=utf-8');
  res.end(req.url==='/qx-wechat/state'?'{}':html);
}).listen(port,'127.0.0.1',()=>console.log('dsh web: http://127.0.0.1:'+port+'/?token=synthetic-'+process.pid));
""",encoding='utf-8')
entry=fixture/'entry.cjs'
entry.write_text("""
const {app,safeStorage,dialog}=require('electron'),path=require('node:path'),fs=require('node:fs');
app.disableHardwareAcceleration();
app.setPath('userData',path.join(process.env.QX_INSTALL_DATA,'.local/desktop-data'));
app.whenReady().then(async()=>{
 const {createModelCredentialStore}=require(process.env.QX_TEST_SOURCE+'/desktop/model-credentials.cjs');
 const saved=await createModelCredentialStore({dataParent:app.getPath('userData'),safeStorage}).save('sk-synthetic-recovery-test-never-real');
 if(saved.status!=='saved')throw Error('Test encryption failed');
 dialog.showMessageBox=async()=>{fs.appendFileSync(process.env.QX_INSTALL_DATA+'/confirmations.txt','confirmed\\n');return {response:1}};
 const runtime=require(process.env.QX_TEST_SOURCE+'/desktop/installed-runtime.cjs'),original=runtime.readRuntime;let first=true;
 runtime.readRuntime=async(...args)=>{if(first){first=false;throw Error('Synthetic initial backend timeout')}return original(...args)};
 fs.copyFileSync(app.getPath('userData')+'/model-credentials/deepseek.bin',process.env.QX_INSTALL_DATA+'/credential-before.bin');
 dialog.showErrorBox=()=>{throw Error('Startup must not display a blocking API/error prompt')};
 require(process.env.QX_TEST_SOURCE+'/desktop/installed.cjs');
}).catch(()=>app.exit(1));
""",encoding='utf-8')
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
env=dict(os.environ,QX_INSTALL_DATA=str(data),QX_PAYLOAD_ROOT=str(payload),QX_TEST_SOURCE=str(ROOT),QX_DESKTOP_HIDDEN='1')
env.pop('ELECTRON_RUN_AS_NODE',None)
executable=Path('D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist/electron.exe')
runtime=data/'.local/runtime.json'
pump=None
def read_runtime():return json.loads(runtime.read_text(encoding='utf-8'))
def wait_for(fn,seconds=30):
    deadline=time.time()+seconds
    while time.time()<deadline:
        if pump:pump.send('Browser.getVersion')
        try:
            value=fn()
            if value:return value
        except (OSError,ValueError,KeyError):pass
        time.sleep(.2)
    raise AssertionError('Timed out waiting for test condition')
def kill(pid,tree=False):
    args=['taskkill','/PID',str(pid),'/F']+(['/T'] if tree else [])
    subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
def stop_host():
    try:
        r=read_runtime();request=urllib.request.Request(r['controlUrl'],method='POST',headers={'Authorization':'Bearer '+r['controlToken']})
        urllib.request.urlopen(request,timeout=5).close()
    except OSError:pass
report={}
stream=(fixture/'electron.log').open('w')
process=subprocess.Popen([str(executable),str(entry),f'--remote-debugging-port={port}','--disable-background-timer-throttling','--disable-renderer-backgrounding'],env=env,stdout=stream,stderr=stream,creationflags=subprocess.CREATE_NO_WINDOW)
try:
    wait_for(lambda:urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=.5).status==200)
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}');context=browser.contexts[0];pump=browser.new_browser_cdp_session()
        wait_for(lambda:len(context.pages)>0,seconds=45);page=context.pages[0]
        expect(page.get_by_role('heading',name='本机服务暂未连接')).to_be_visible(timeout=30000)
        assert not any('setup.html' in other.url for other in context.pages)
        expect(page.locator('#api-key')).to_have_count(0)
        report['startupFailureShowsRecoveryInsteadOfApiSetup']=True
        button=page.get_by_role('button',name='重新连接',exact=True);expect(button).to_be_visible(timeout=45000);button.click()
        wait_for(lambda:len(context.pages)==1 and context.pages[0]!=page,seconds=30)
        page=context.pages[0];expect(page.get_by_role('textbox',name='未发送内容')).to_be_visible(timeout=30000)
        assert page.url==read_runtime()['url']
        assert (data/'credential-before.bin').read_bytes()==(data/'.local/desktop-data/model-credentials/deepseek.bin').read_bytes()
        assert not (data/'confirmations.txt').exists()
        report.update(reconnectedWithExistingEncryptedKey=True,noCredentialWrite=True,noModelRequest=True)
        page.close();process.wait(timeout=15);browser.close()
finally:
    stop_host()
    if process.poll() is None:kill(process.pid,tree=True)
    stream.close()
(out/'startup-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
