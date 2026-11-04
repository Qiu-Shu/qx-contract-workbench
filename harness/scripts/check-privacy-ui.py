"""Isolated browser intake test; synthetic files only, no real user sessions."""
import json
from pathlib import Path
import time
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.local/privacy-ui-check'/time.strftime('%Y%m%d-%H%M%S')
OUT.mkdir(parents=True)
HTML='''<html lang="zh-CN"><meta charset="utf-8"><style>body{font:14px/1.6 system-ui;margin:70px auto;max-width:760px;background:#f7f8fa} [data-composer-card]{padding:14px;background:white;border:1px solid #dce2eb;border-radius:14px} [contenteditable]{min-height:100px;padding:12px;outline:none} button{padding:8px 20px} ul{overflow-wrap:anywhere} input{max-width:100%}.qx-kb{background:white;padding:20px;margin-top:40px}</style><div data-composer-card><input type="file" id="chatfiles" multiple><div role="textbox" contenteditable="true">合成验收输入框</div><button aria-label="发送">发送</button><ul id="received"></ul></div><div class="qx-kb"><div class="qx-kb-toolbar"><input type="file" id="knowledge" multiple accept=".txt,.docx,.png"><input type="file" id="restore" accept=".zip"></div></div><script>window.received=[];window.raw=[];for(const type of ['change','paste','drop'])document.addEventListener(type,async e=>{const files=e.type==='change'?e.target.files:(e.clipboardData||e.dataTransfer).files;for(const file of files||[]){const entry={event:type,name:file.name,text:await file.text(),target:e.target.id};received.push(entry);document.getElementById('received').textContent=JSON.stringify(received);}})</script></html>'''

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1000,'height':850})
    calls=[]
    def route(request):
        calls.append(request.request.post_data_buffer.decode())
        if 'FAIL' in calls[-1]:request.fulfill(status=400,content_type='application/json',body=json.dumps({'error':'识字失败，原件未发送。'}));return
        mode=parse_qs(urlsplit(request.request.url).query).get('mode',['standard'])[0]
        request.fulfill(status=200,headers={'content-type':'application/json','x-qx-privacy-mode':mode},body=json.dumps({'document_id':'synthetic-id',
            'review_token':'synthetic-token','original_text':'PRIVATE','safe_text':'姓名：[人物1]。金额1000元。','replacements':[],'privacy_mode':mode,'replacement_count':1}))
    page.route('http://127.0.0.1:37213/api/qx-privacy/prepare?*',route)
    page.route('http://127.0.0.1:37213/api/qx-privacy/review.js',lambda r:r.fulfill(content_type='text/javascript',body=(ROOT/'plugins/privacy/review.js').read_text(encoding='utf8')))
    page.route('http://127.0.0.1:37213/api/qx-privacy/confirm',lambda r:r.fulfill(headers={'content-type':'text/plain','x-qx-safe-name':'safe.txt','x-qx-reviewed':'test'},body=r.request.post_data_json['text']))
    page.route('http://127.0.0.1:37213/',lambda r:r.fulfill(content_type='text/html',body=HTML))
    page.goto('http://127.0.0.1:37213/')
    page.add_script_tag(path=str(ROOT/'plugins/privacy/client.js'))
    check=page.locator('[data-composer-card] input[type=checkbox]')
    expect(check).not_to_be_checked()
    page.locator('#chatfiles').set_input_files({'name':'normal.txt','mimeType':'text/plain','buffer':b'UNCHANGED'})
    page.wait_for_function('received.length===1');assert page.evaluate('received[0].text')=='UNCHANGED' and not calls
    check.check()
    page.locator('#chatfiles').set_input_files({'name':'private.txt','mimeType':'text/plain','buffer':b'PRIVATE'})
    page.get_by_role('button',name='确认使用此版本',exact=True).click()
    page.wait_for_function('received.length===2');assert page.evaluate('received[1].name')=='safe.txt', page.evaluate('JSON.stringify(received)')
    for kind in ['paste','drop']:
        page.locator('[contenteditable]').evaluate('''(el,type)=>{const dt=new DataTransfer();dt.items.add(new File(['PRIVATE'],'image.png',{type:'image/png'}));el.dispatchEvent(type==='paste'?new ClipboardEvent(type,{bubbles:true,cancelable:true,clipboardData:dt}):new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:dt}));}''',kind)
        page.get_by_role('button',name='确认使用此版本',exact=True).click()
        page.wait_for_function(f'received.length==={3 if kind=="paste" else 4}')
    assert all(x['text'].startswith('姓名：[人物1]') for x in page.evaluate('received.slice(1)'))
    page.locator('.qx-kb input[type=checkbox]').check()
    page.locator('#knowledge').set_input_files({'name':'k.txt','mimeType':'text/plain','buffer':b'PRIVATE'})
    page.get_by_role('button',name='确认使用此版本',exact=True).click()
    page.wait_for_function('received.length===5');assert page.evaluate('received[4].text').startswith('姓名：[人物1]')
    page.locator('#restore').set_input_files({'name':'backup.zip','mimeType':'application/zip','buffer':b'BACKUP'})
    page.wait_for_function('received.length===6');assert page.evaluate('received[5].text')=='BACKUP'
    page.locator('#chatfiles').set_input_files({'name':'bad.png','mimeType':'image/png','buffer':b'FAIL'})
    expect(page.locator('[data-composer-card] [role=status]')).to_contain_text('原件未发送')
    assert page.evaluate('received.length')==6
    page.screenshot(path=str(OUT/'desktop.png'))
    page.set_viewport_size({'width':420,'height':850});page.screenshot(path=str(OUT/'narrow.png'))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.evaluate('window.qxPrivacy.dispose()');assert page.locator('.qx-privacy').count()==0
    browser.close()
    (OUT/'report.json').write_text(json.dumps({'passed':True,'checks':['default off','file picker','clipboard image','drag image','knowledge upload','ZIP bypass','failure no raw replay','narrow layout','dispose']},ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(OUT))
