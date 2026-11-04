"""Real local Python/Node/Chromium review workflow with fictional data only."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from playwright.sync_api import sync_playwright, expect
from check_privacy_end_to_end import HOST, HTML, ROOT

OUT=ROOT/'.local/privacy-review-check'/time.strftime('%Y%m%d-%H%M%S')
OUT.mkdir(parents=True)
(OUT/'host.mjs').write_text(HOST,encoding='utf8')
(OUT/'fixture.html').write_text(HTML,encoding='utf8')
node='C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
python='D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe'
errors=[]
with (OUT/'stderr.log').open('w',encoding='utf8') as stderr:
    host=subprocess.Popen([node,str(OUT/'host.mjs'),str(ROOT/'plugins/privacy/index.mjs'),python,str(OUT),str(OUT/'fixture.html')],stdout=subprocess.PIPE,stderr=stderr,text=True,encoding='utf8')
    ready=queue.Queue();threading.Thread(target=lambda:ready.put(host.stdout.readline()),daemon=True).start()
    try:
        origin=json.loads(ready.get(timeout=20))['origin']
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1280,'height':950})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
            page.goto(origin);page.locator('input[type=checkbox]').check()
            source='姓名：李明。电话13800138000。合同金额8000元。专属事项晨露工程，晨露工程需要复核。\n<script>window.leaked=true</script>'
            def add(text=source,name='虚构合同.txt'):
                page.locator('#chatfiles').set_input_files({'name':name,'mimeType':'text/plain','buffer':text.encode()})
            def panel():
                element=page.get_by_role('dialog',name='脱敏复核',exact=True)
                expect(element).to_be_visible(timeout=15000)
                return element
            def count():return page.evaluate('received.length')
            def selected(editor,value):
                editor.evaluate('(el,s)=>{const at=el.value.indexOf(s);if(at<0)throw Error("selection absent");el.focus();el.setSelectionRange(at,at+s.length);el.dispatchEvent(new Event("select"));}',value)
            def confirm():panel().get_by_role('button',name='确认使用此版本',exact=True).click()
            def wait(n):page.wait_for_function('(n)=>received.length===n',arg=n)
            add();dialog=panel();assert count()==0
            editor=dialog.get_by_role('textbox',name='最终发送文字',exact=True)
            initial=editor.input_value();assert '李明' not in initial and '13800138000' not in initial
            dialog.get_by_text('原文对照（仅本机）',exact=True).click()
            assert '李明' in dialog.locator('[data-original]').inner_text()
            assert page.evaluate('window.leaked') is None
            selected(editor,'晨露工程');dialog.get_by_label('同时处理全部相同文字').check()
            dialog.get_by_role('button',name='脱敏选中文字',exact=True).click()
            assert '晨露工程' not in editor.input_value()
            dialog.get_by_role('button',name='撤销上一步',exact=True).click();assert editor.input_value()==initial
            selected(editor,'晨露工程');dialog.get_by_role('button',name='脱敏选中文字',exact=True).click()
            token=editor.input_value().split('专属事项')[1].split('，')[0]
            selected(editor,token);dialog.get_by_role('button',name='恢复所选原文',exact=True).click()
            assert editor.input_value().count('晨露工程')==2
            selected(editor,'晨露工程');dialog.get_by_role('button',name='脱敏选中文字',exact=True).click()
            editor.fill(editor.input_value()+'\n律师确认版本。');final=editor.input_value()
            for width in [1280,420,320]:
                page.set_viewport_size({'width':width,'height':950})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(OUT/f'review-{width}.png'),full_page=True)
            page.set_viewport_size({'width':1280,'height':950})
            assert count()==0;confirm();wait(1)
            assert page.evaluate('received[0].text')==final
            assert page.evaluate('received[0].name').startswith('已复核脱敏文字-')
            # Cancellation never returns even the automatic safe file.
            add();panel().get_by_role('button',name='取消本批',exact=True).click()
            expect(page.locator('.qx-privacy')).to_have_attribute('data-busy','false');assert count()==1
            # Each document needs a decision; release a batch only when all accepted.
            page.locator('#chatfiles').set_input_files([{'name':f'{i}.txt','mimeType':'text/plain','buffer':source.encode()} for i in [1,2]])
            confirm();panel();assert count()==1;confirm();wait(3)
            # A pending reviewer is invalidated when its source session changes.
            add();panel();page.evaluate("document.documentElement.dataset.qxSessionId='different'")
            expect(page.get_by_role('dialog',name='脱敏复核',exact=True)).not_to_be_visible();assert count()==3
            page.locator('input[type=checkbox]').check()
            # Confirm failure keeps the editable draft, then retry succeeds.
            add();dialog=panel();page.route(origin+'/api/qx-privacy/confirm',lambda r:r.abort())
            confirm();expect(dialog.locator('[role=status]')).to_contain_text('重试');assert count()==3
            page.unroute(origin+'/api/qx-privacy/confirm');confirm();wait(4)
            # Concurrent batches serialize their review panels and preserve their content.
            add('姓名：张三。第一批。');panel();add('姓名：王五。第二批。')
            confirm();wait(5);panel();confirm();wait(6)
            assert '第一批' in page.evaluate('received[4].text') and '第二批' in page.evaluate('received[5].text')
            held=[]
            page.route(origin+'/api/qx-privacy/prepare?*',lambda r:held.append(r))
            add();page.wait_for_timeout(100);assert held
            page.evaluate("document.documentElement.dataset.qxSessionId='away'")
            page.evaluate("document.documentElement.dataset.qxSessionId='different'")
            page.unroute(origin+'/api/qx-privacy/prepare?*')
            try:held.pop().continue_()
            except Exception:pass  # An aborted held request no longer has a transport.
            expect(page.locator('.qx-privacy')).to_have_attribute('data-busy','false')
            expect(page.locator('.qx-privacy [role=status]')).to_contain_text('已取消')
            expect(page.get_by_role('dialog',name='脱敏复核',exact=True)).not_to_be_visible();assert count()==6
            assert not errors,errors
            assert all('李明' not in item['text'] and '13800138000' not in item['text'] for item in page.evaluate('received'))
            browser.close()
        (OUT/'report.json').write_text(json.dumps({'passed':True,'uploads':6,'models_called':0,'errors':errors,'checks':['confirmation gate','original private comparison','manual all-match redaction','undo','restore','exact final bytes','cancel','batch','session switch','failed confirm retry','concurrent queue','no HTML execution','1280/420/320 layout']},ensure_ascii=False,indent=2),encoding='utf8')
        print(OUT)
    finally:
        host.terminate();host.wait(timeout=20)
