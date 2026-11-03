"""Exercise only an isolated new profile; no real key or model task."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
stage=ROOT/'.local/package-20261103-b'
out=ROOT/'docs/checks/installer'
out.mkdir(parents=True,exist_ok=True)
profile=ROOT/'.local/installer-check-首次配置'
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
env=dict(os.environ,QX_INSTALL_DATA=str(profile),QX_PAYLOAD_ROOT=str(stage/'workbench'),QX_DESKTOP_HIDDEN='1')
env.pop('ELECTRON_RUN_AS_NODE',None)
electron='D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist/electron.exe'
with (out/'first-run.log').open('w') as log:
    process=subprocess.Popen([electron,f'--remote-debugging-port={port}',str(ROOT/'desktop/installed.cjs')],env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(120):
            try:urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=.5).close();break
            except Exception:time.sleep(.25)
        with sync_playwright() as playwright:
            browser=playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
            page=browser.contexts[0].pages[0]
            page.wait_for_selector('#api-key')
            assert page.title()=='配置 API · 群兴法律工作台'
            page.locator('#api-key').fill('tiny')
            page.locator('#submit').click()
            page.get_by_text('请填写完整的 DeepSeek API Key。',exact=True).wait_for()
            assert not (profile/'.local/desktop-data/model-credentials/deepseek.bin').exists()
            page.locator('#reveal').click();assert page.locator('#api-key').get_attribute('type')=='text'
            page.locator('#reveal').click();assert page.locator('#api-key').get_attribute('type')=='password'
            page.locator('#api-key').fill('')
            page.screenshot(path=str(out/'first-run.png'),full_page=True)
            page.set_viewport_size({'width':460,'height':650})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(out/'first-run-small.png'),full_page=True)
            result={'firstRunGuide':True,'invalidKeyNotStored':True,'showHide':True,'narrowNoHorizontalOverflow':True,'noModelRequest':True}
            (out/'first-run.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result))
            browser.close()
    finally:
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
