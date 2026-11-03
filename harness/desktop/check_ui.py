"""Exercise the real Electron shell and Harness UI with fictional attachments.

Requires the running host and prepared shared session. Never presses Send.
The two paste checks place only synthetic content into the Windows clipboard.
"""
import json, os, re, socket, subprocess, sys, time, urllib.request
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parents[1]
drop_only='--drop-only' in sys.argv
out=root/'desktop'/'checks'/time.strftime('%Y%m%d-%H%M%S')
out.mkdir(parents=True)
sample=out/'虚构验收条款.txt'
sample.write_text('纯合成桌面验收材料。付款期限：验收合格后十日内。',encoding='utf8')
copied=out/'虚构复制材料.txt'
copied.write_text('这是资源管理器复制文件粘贴的合成材料。',encoding='utf8')
picture=out/'虚构图片.png'
im=Image.new('RGB',(1000,260),'white');draw=ImageDraw.Draw(im)
draw.text((35,70),'合成图片：验收后十日内付款',font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',46),fill='black')
im.save(picture)
with socket.socket() as listener:
    listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
env=dict(os.environ);env.pop('ELECTRON_RUN_AS_NODE',None)
env.update(QX_DESKTOP_DATA=str(out/'desktop-data'),QX_DESKTOP_HIDDEN='1')
electron='D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist/electron.exe'
log=(out/'electron.log').open('w',encoding='utf8')
process=subprocess.Popen([electron,f'--remote-debugging-port={port}','--remote-debugging-address=127.0.0.1',str(root/'desktop/main.cjs')],
                         cwd=root,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
report={'status':'running','scope':'Real Electron + official Harness host; fictional files only; no message sent or model called',
        'checks':[],'uploads':[],'page_errors':[]}
browser=None
def ps(script):
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-STA','-Command',script],
                          creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True,text=True,timeout=15)
    if result.returncode: raise RuntimeError('Synthetic clipboard preparation failed')
def ps_literal(value): return "'"+str(value).replace("'","''")+"'"
try:
    for _ in range(150):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=.5).close();break
        except Exception:
            if process.poll() is not None: raise RuntimeError('Desktop process stopped')
            time.sleep(.2)
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
        page=browser.contexts[0].pages[0]
        page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
        def response(value):
            if '/api/session/uploadFileBinary' in value.url:
                query=parse_qs(urlparse(value.url).query)
                report['uploads'].append({'status':value.status,'name':query.get('name',[None])[0],
                                          'kind':'image' if 'mediaType' in query else 'file'})
        page.on('response',response)
        try:
            page.get_by_role('dialog',name='预览版说明').get_by_role('button',name='继续',exact=True).click(timeout=10000)
        except Exception: pass
        shared=page.evaluate("fetch('/qx-wechat/state').then(response=>response.json()).then(state=>state.sessionId)")
        expect(page.locator('html')).to_have_attribute('data-qx-session-id',shared,timeout=60000)
        report['startup_session_id']=shared
        report['checks'].append('Desktop startup selected the persisted WeChat session without modifying its binding')
        # All attachment operations use a known synthetic session, never the user's current contract.
        group=page.get_by_role('treeitem',name='未分组',exact=True)
        if group.count() and group.get_attribute('aria-expanded')!='true':group.click()
        page.get_by_role('treeitem',name=re.compile('群兴合成运行验证 2026-11-03T03-04-24-316Z')).first.click()
        expect(page.locator('html')).to_have_attribute('data-qx-session-id','qx-smoke-4e02792a-de51-4e60-850d-1ba9ed875e81',timeout=30000)
        editor=page.locator('[data-composer-input][contenteditable="true"]')
        expect(editor).to_be_visible(timeout=60000)
        expect(page.get_by_text('群兴工作区',exact=True).first).to_be_visible()
        report['checks'].append('Synthetic session selected; editable official composer')
        if drop_only:
            data=page.evaluate_handle('''({name,text})=>{const data=new DataTransfer();data.items.add(new File([text],name,{type:'text/plain'}));return data;}''',{'name':sample.name,'text':sample.read_text(encoding='utf8')})
            editor.dispatch_event('dragenter',{'dataTransfer':data})
            editor.dispatch_event('dragover',{'dataTransfer':data})
            editor.dispatch_event('drop',{'dataTransfer':data})
            expect(page.get_by_text(sample.name,exact=True).first).to_be_visible(timeout=30000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out/'3-drop-file.png'))
            report['checks'].append('Real File/DataTransfer drop event on official composer; attachment card visible; upload API not mocked')
        else:
            page.locator('[data-composer-card] input[type="file"]').set_input_files(str(sample))
            expect(page.get_by_text(sample.name,exact=True).first).to_be_visible(timeout=30000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out/'1-file-card.png'))
            report['checks'].append('Native file input selected TXT; official attachment card visible')
            ps("Add-Type -AssemblyName System.Windows.Forms; $list=New-Object System.Collections.Specialized.StringCollection; $list.Add("+ps_literal(copied)+") | Out-Null; [System.Windows.Forms.Clipboard]::SetFileDropList($list)")
            editor.click();page.keyboard.press('Control+V')
            expect(page.get_by_text(copied.name,exact=True).first).to_be_visible(timeout=30000)
            report['checks'].append('Actual Windows Explorer FileDropList pasted with Ctrl+V into official attachment card')
            ps("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; $image=[Drawing.Image]::FromFile("+ps_literal(picture)+"); [System.Windows.Forms.Clipboard]::SetImage($image); $image.Dispose()")
            editor.click();page.keyboard.press('Control+V')
            page.wait_for_function("Array.from(document.querySelectorAll('[data-composer-card] img')).some(image => image.naturalWidth > 0)",timeout=30000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out/'2-file-and-image-paste.png'))
            report['checks'].append('Actual Windows bitmap clipboard pasted with Ctrl+V; image thumbnail decoded')
        assert len(report['uploads'])>=(1 if drop_only else 3), report['uploads']
        assert all(upload['status']==200 for upload in report['uploads']), report['uploads']
        assert not report['page_errors'], report['page_errors']
        report['status']='passed'
        browser.close();browser=None
except Exception as error:
    report['status']='failed';report['error']=str(error).replace(str(root),'PROJECT')
    try:
        if page.locator('html').get_attribute('data-qx-session-id')=='qx-smoke-4e02792a-de51-4e60-850d-1ba9ed875e81':page.screenshot(path=str(out/'failure.png'))
    except Exception: pass
    raise
finally:
    if browser:
        try: browser.close()
        except Exception: pass
    process.terminate()
    try: process.wait(timeout=10)
    except subprocess.TimeoutExpired: process.kill()
    log.close()
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'status':report['status'],'report':str(out/'report.json')},ensure_ascii=False))
