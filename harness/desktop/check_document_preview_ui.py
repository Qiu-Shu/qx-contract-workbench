"""Check real right-pane preview against an isolated host and locally mocked model."""
import json,os,re,subprocess,sys,time,urllib.request
from urllib.parse import urlsplit
from pathlib import Path
sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'.local/document-preview-20261104'
data=out/('ui-'+str(int(time.time())));data.mkdir()
stream=(data/'launcher.log').open('w')
host=subprocess.Popen(['node',str(ROOT/'desktop/check_document_preview_host.cjs'),str(data)],cwd=ROOT,stdout=stream,stderr=stream,creationflags=subprocess.CREATE_NO_WINDOW)
runtime=data/'.local/runtime.json';report={};errors=[]
def wait_runtime():
    deadline=time.time()+150
    while time.time()<deadline:
        if host.poll() is not None:raise AssertionError('Test host exited')
        try:
            r=json.loads(runtime.read_text(encoding='utf-8'))
            if r.get('url'):
                address=urlsplit(r['url']);urllib.request.urlopen(f'{address.scheme}://{address.netloc}/qx-wechat/state',timeout=2).close();return r
        except (OSError,ValueError):pass
        time.sleep(.5)
    raise AssertionError('Test host did not become ready')
try:
    r=wait_runtime();print('Isolated full workbench ready',flush=True)
    p=sync_playwright().start()
    if True:
        browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True,args=['--disable-gpu'])
        context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
        context.add_init_script("window.__DSH_LOCALE__={read:async()=>({languages:['zh-CN'],preference:'zh'}),onChange:()=>{}}")
        context.route('**/api/qx-account/balance*',lambda route:route.fulfill(json={'status':'unavailable','balances':[]}))
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(r['url'],wait_until='domcontentloaded')
        page.get_by_role('button',name='开始使用',exact=True).click(timeout=60000)
        expect(page.get_by_role('button',name='开始使用',exact=True)).to_have_count(0,timeout=60000)
        editor=page.locator('[data-composer-input][contenteditable=true]').first;expect(editor).to_be_visible(timeout=60000)
        editor.fill('这是合成的预览测试。')
        expect(page.locator('#root')).not_to_have_attribute('inert','')
        print('Upload inputs:',page.locator('input[type=file]').evaluate_all('(els)=>els.map(e=>({accept:e.accept,disabled:e.disabled,composer:!!e.closest("[data-composer-card]")}))'),flush=True)
        page.locator('[data-composer-card] input[type=file]').first.set_input_files(str(out/'fixtures/预览测试.docx'))
        preview=page.get_by_role('button',name='预览 预览测试.docx',exact=True)
        expect(preview).to_be_visible(timeout=30000);page.screenshot(path=str(out/'before-preview.png'));preview.click()
        expect(page.locator('canvas').first).to_be_visible(timeout=120000)
        expect(page.get_by_text('Office 预览不可用',exact=False)).to_have_count(0)
        page.screenshot(path=str(out/'uploaded-word-preview.png'));report['draftUploadRightPreview']=True
        editor.fill('这是合成的预览测试，请直接回复测试完成。');editor.press('Enter')
        historical=page.locator('[data-message-attachments]').get_by_role('button',name='预览 预览测试.docx',exact=True)
        expect(historical).to_be_visible(timeout=30000);historical.click()
        expect(page.locator('canvas').first).to_be_visible(timeout=60000);report['historicalUploadRightPreview']=True
        expect(page.get_by_text('这是本机预览测试的模拟回复。',exact=False).first).to_be_visible(timeout=30000)
        page.get_by_text('生成的文档.docx',exact=True).click()
        expect(page.locator('[data-document-preview]:visible canvas').first).to_be_visible(timeout=60000)
        expect(page.locator('[data-textpreview-path]:visible')).to_contain_text('生成的文档.docx')
        report['generatedWordRightPreview']=True
        (out/'fixtures/预览测试.pdf').write_bytes((out/'converted/预览测试-docx.pdf').read_bytes())
        for filename in ['预览测试.xlsx','预览测试.pptx','预览测试.pdf','文字测试.txt']:
            page.locator('[data-composer-card] input[type=file]').first.set_input_files(str(out/'fixtures'/filename))
            button=page.get_by_role('button',name='预览 '+filename,exact=True);expect(button).to_be_visible(timeout=30000);button.click()
            expect(page.locator('[data-textpreview-path]:visible')).to_contain_text(filename)
            if filename.endswith('.txt'):expect(page.get_by_text('合成文本预览：文件内容可以读取。',exact=False).first).to_be_visible(timeout=30000)
            elif filename.endswith('.xlsx'):expect(page.locator('[data-excel-preview]:visible canvas').first).to_be_visible(timeout=60000)
            else:expect(page.locator('[data-document-preview]:visible canvas').first).to_be_visible(timeout=120000)
            page.screenshot(path=str(out/(filename+'.png')));report[filename]=True
            print('Verified:',filename,flush=True)
        page.locator('[data-composer-card] input[type=file]').first.set_input_files(str(out/'fixtures/图片测试.png'))
        image=page.locator('[data-composer-card] button').filter(has=page.locator('img')).last
        expect(image).to_be_visible(timeout=30000);image.click()
        expect(page.get_by_role('dialog').last).to_be_visible(timeout=30000)
        report['imageLightboxPreview']=True
        page.screenshot(path=str(out/'uploaded-multiple-preview.png'))
        report['pageErrors']=errors;assert not errors,errors
        browser.close()
except Exception:
    try:
        page.screenshot(path=str(out/'ui-failure.png'))
        (out/'ui-failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
    except Exception:pass
    raise
finally:
    (out/'ui-report.json').write_text(json.dumps({**report,'pageErrors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    try:browser.close();p.stop()
    except Exception:pass
    try:
        r=json.loads(runtime.read_text());req=urllib.request.Request(r['controlUrl'],method='POST',headers={'Authorization':'Bearer '+r['controlToken']});urllib.request.urlopen(req,timeout=5).close()
        host.wait(timeout=20)
    except Exception:
        if host.poll() is None:subprocess.run(['taskkill','/PID',str(host.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    stream.close()
(out/'ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
