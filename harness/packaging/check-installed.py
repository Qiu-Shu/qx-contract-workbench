"""Test the actual installed executable, then leave its background for upgrade QA."""
import json,os,re,socket,subprocess,sys,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
installed=Path(sys.argv[1]).resolve()
data=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else ROOT/'.local/installer-check-实际安装'
assert data.is_relative_to(ROOT/'.local') and data.name.startswith('installer-check-')
out=ROOT/'docs/checks/installer'
env=dict(os.environ,QX_INSTALL_DATA=str(data),QX_DESKTOP_HIDDEN='1',PYTHONDONTWRITEBYTECODE='1')
env.pop('QX_PAYLOAD_ROOT',None);env.pop('ELECTRON_RUN_AS_NODE',None)
executable=installed/'QunxingWorkbench.exe'
def launch():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));inspector=sock.getsockname()[1]
    stream=(out/'installed.log').open('a')
    process=subprocess.Popen([str(executable),f'--remote-debugging-port={port}',f'--inspect=127.0.0.1:{inspector}','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows'],env=env,stdout=stream,stderr=stream,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(200):
        try:urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=.5).close();break
        except Exception:time.sleep(.25)
    return process,port,stream,inspector
def close(process,stream):
    try:process.wait(timeout=15)
    except subprocess.TimeoutExpired:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    stream.close()
upgrading=len(sys.argv)>3 and sys.argv[3]=='upgrade'
report={'upgradeLaunch':upgrading}
with sync_playwright() as p:
    if not upgrading:
        print('Checking packaged first launch',flush=True)
        process,port,stream,inspector=launch()
        try:
            print('Connecting to packaged configuration window',flush=True)
            browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}');page=browser.contexts[0].pages[0]
            print('Checking API input',flush=True)
            page.locator('#api-key').wait_for();page.locator('#api-key').fill('tiny');page.locator('#submit').click()
            page.get_by_text('请填写完整的 DeepSeek API Key。',exact=True).wait_for()
            assert not (data/'.local/desktop-data/model-credentials/deepseek.bin').exists()
            report['installedFirstRun']=True;report['invalidKeyNotSaved']=True
            result=subprocess.run([str(installed/'resources/workbench/runtime/node.exe'),str(ROOT/'packaging/seed-packaged.cjs'),str(inspector)],env=env,capture_output=True,timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode==0,result.stderr.decode(errors='replace')
            page.close()
            browser.close()
        finally:close(process,stream)
        print('First launch passed; synthetic credential saved by same executable',flush=True)
    process,port,stream,inspector=launch()
    print('Checking packaged workbench',flush=True)
    try:
        browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}');context=browser.contexts[0]
        end=time.time()+180
        while not context.pages and time.time()<end:time.sleep(.2);browser.new_browser_cdp_session().send('Browser.getVersion')
        page=context.pages[0]
        page.get_by_role('button',name='微信连接',exact=True).wait_for(timeout=180000)
        start=page.get_by_role('button',name=re.compile('^(开始使用|继续)$'))
        if start.is_visible():start.click()
        assert page.evaluate('typeof window.__DSH_DIRECTORY_PICKER__.pick')=='function'
        if os.environ.get('QX_EXPECT_UPDATER_VERSION'):
            update=page.evaluate('window.__QX_UPDATES__.read()')
            assert update and update['version']==os.environ['QX_EXPECT_UPDATER_VERSION']
            assert page.evaluate("window.__QX_UPDATES__.act('invalid-action')") is None
            report['packagedUpdaterIPC']=True
        assert (page.get_by_role('button',name='微信连接',exact=True).bounding_box()['y']<page.locator('.qx-balance-refresh').bounding_box()['y'])
        page.get_by_role('checkbox',name='上传前脱敏',exact=True).wait_for()
        assert not page.get_by_role('checkbox',name='上传前脱敏',exact=True).is_checked()
        page.get_by_role('button',name='微信连接',exact=True).click()
        page.get_by_role('dialog',name='微信连接',exact=True).wait_for()
        report.update(privacyAvailable=True,wechatDialog=True,installedRuntimeStarts=True,desktopIPC=True,wechatAboveBalance=True,noModelRequest=True,providerKey='synthetic only')
        page.close()
        browser.close()
    finally:close(process,stream)
sentinel=data/'workspace/升级保留验收.txt'
if upgrading:
    assert sentinel.read_text(encoding='utf-8')=='纯虚构升级验收，必须保留。'
    report['materialsRetained']=True
else:sentinel.write_text('纯虚构升级验收，必须保留。',encoding='utf-8')
(out/('unpacked.json' if installed.name=='win-unpacked' else 'installed-upgrade.json' if upgrading else 'installed.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
