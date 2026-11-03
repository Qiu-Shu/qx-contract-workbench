import json,os,socket,subprocess,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'docs/checks/installer';out.mkdir(parents=True,exist_ok=True)
data=ROOT/('.local/installer-check-成功转场-'+time.strftime('%H%M%S'))
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
env=dict(os.environ,QX_INSTALL_DATA=str(data),QX_PAYLOAD_ROOT=str(ROOT/'.local/package-20261103-b/workbench'),QX_DESKTOP_HIDDEN='1')
env.pop('ELECTRON_RUN_AS_NODE',None)
log=(out/'transition.log').open('w')
process=subprocess.Popen(['D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist/electron.exe',f'--remote-debugging-port={port}',str(ROOT/'packaging/check-transition.cjs')],env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(160):
        try:urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=.5).close();break
        except Exception:time.sleep(.25)
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
        context=browser.contexts[0]
        page=context.pages[0];page.wait_for_selector('#api-key')
        page.locator('#api-key').fill('sk-synthetic-transition-test-key')
        with context.expect_page(timeout=180000) as opening:page.locator('#submit').click()
        main=opening.value
        main.get_by_role('button',name='微信连接',exact=True).wait_for(timeout=90000)
        notice=main.get_by_role('button',name='继续',exact=True)
        if notice.is_visible():notice.click()
        link=main.get_by_role('button',name='微信连接',exact=True).bounding_box()
        balance=main.locator('.qx-balance-refresh').bounding_box()
        assert link['y']<balance['y'],'WeChat link must be above balance'
        assert page.is_closed(),'Setup must close after main is ready'
        cipher=(data/'.local/desktop-data/model-credentials/deepseek.bin').read_bytes()
        assert b'sk-synthetic' not in cipher
        old_url=main.url
        print('First configuration transition passed',flush=True)
        with context.expect_page(timeout=15000) as opening:(data/'test-open-settings').write_text('open')
        setup=opening.value
        setup.locator('#api-key').fill('sk-synthetic-transition-second-key')
        with context.expect_page(timeout=180000) as opening:setup.locator('#submit').click()
        new=opening.value
        new.get_by_role('button',name='微信连接',exact=True).wait_for(timeout=90000)
        notice=new.get_by_role('button',name='继续',exact=True)
        if notice.is_visible():notice.click()
        assert main.is_closed(),'Changing API must replace window with updated IPC origin'
        assert new.evaluate('typeof window.__DSH_DIRECTORY_PICKER__.pick')=='function'
        locale=new.evaluate('window.__DSH_LOCALE__.read()')
        assert locale['preference']=='zh'
        assert new.url!=old_url
        new.get_by_role('button',name='微信连接',exact=True).click()
        new.get_by_role('dialog',name='微信连接',exact=True).wait_for()
        report={'providerVerification':'simulated acceptance of synthetic key only','realEncryption':True,'firstSaveToMain':True,'wechatAboveBalance':True,'apiChangeRecreatesWindow':True,'wechatDialogOpens':True,'noModelRequest':True}
        (out/'transition.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report))
        browser.close()
finally:
    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    runtime=data/'.local/runtime.json'
    if runtime.exists():
        info=json.loads(runtime.read_text())
        for name in ['launcherPid','hostPid']:
            if info.get(name):subprocess.run(['taskkill','/PID',str(info[name]),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    log.close()
