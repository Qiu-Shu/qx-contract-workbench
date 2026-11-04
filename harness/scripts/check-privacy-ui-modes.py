"""Isolated Chromium mode/intake checks: synthetic files and mocked local endpoints only."""
import json
from pathlib import Path
import time
from urllib.parse import parse_qs, unquote, urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.local/privacy-improvement-20261104'/('ui-'+time.strftime('%Y%m%d-%H%M%S'))
OUT.mkdir(parents=True)
ORIGIN='http://127.0.0.1:37213'
HTML='''<html lang="zh-CN"><meta charset="utf-8"><style>
*{box-sizing:border-box}body{font:14px/1.6 system-ui;margin:32px auto;padding:0 12px;max-width:760px;background:#f7f8fa;color:#263344}
h1{font-size:24px}h2{font-size:17px;margin:0 0 12px}[data-composer-card]{padding:14px;background:white;border:1px solid #dce2eb;border-radius:14px}
[contenteditable]{min-height:90px;padding:12px;outline:none}button{padding:8px 20px}input{max-width:100%}.qx-kb{background:white;padding:20px;margin-top:24px;border-radius:14px}
#received{overflow-wrap:anywhere;white-space:pre-wrap;max-height:90px;overflow:auto;font:12px/1.6 system-ui}
</style><h1>上传资料脱敏</h1><div data-composer-card><input type="file" id="chatfiles" multiple><div role="textbox" contenteditable="true">描述本次需要处理的法律事项，或添加文档与图片。</div><button aria-label="发送">发送</button><pre id="received"></pre></div>
<div class="qx-kb"><h2>律所知识库</h2><div class="qx-kb-toolbar"><input type="file" id="knowledge" multiple accept=".txt,.docx,.png"><input type="file" id="restore" accept=".zip"></div></div>
<script>window.received=[];window.sent=0;document.querySelector('button').addEventListener('click',()=>sent++);
for(const type of ['change','paste','drop'])document.addEventListener(type,async e=>{
const files=e.type==='change'?e.target.files:(e.clipboardData||e.dataTransfer)?.files;
for(const file of files||[]){received.push({event:type,name:file.name,text:await file.text(),target:e.target.id});
document.getElementById('received').textContent=received.map(x=>x.name).join(' · ');
if(e.target.id==='restore')continue;
if(e.target.closest?.('.qx-kb'))await fetch('/api/qx-knowledge/upload?name='+encodeURIComponent(file.name),{method:'POST',body:file});
else{const xhr=new XMLHttpRequest();xhr.open('POST','/api/session/uploadFileBinary?name='+encodeURIComponent(file.name));xhr.send(file);}}});</script></html>'''

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1000,'height':1100})
    calls,uploads,held,checks,errors=[],[],[],[],[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def complete(route,params,body):
        mode=params.get('mode',[''])[0]
        if body=='FAIL':route.fulfill(status=400,content_type='application/json',body=json.dumps({'error':'识字失败，原件未发送。'}));return
        if body=='NETWORK':route.abort('failed');return
        headers={'content-type':'text/plain','x-qx-safe-name':f'{mode}-safe.txt','x-qx-replacements':'1'}
        if body!='MISSING_MODE':headers['x-qx-privacy-mode']='standard' if body=='WRONG_MODE' else mode
        route.fulfill(status=200,headers=headers,body=f'姓名：【人物1】。方式：{mode}。金额1000元。')
    def prepare(route):
        request=route.request;body=request.post_data_buffer.decode();params=parse_qs(urlsplit(request.url).query)
        calls.append({'body':body,'mode':params.get('mode',[''])[0],'context':params.get('context',[''])[0],
                      'terms':json.loads(unquote(request.headers.get('x-qx-terms','%5B%5D')))})
        if body.startswith('HOLD'):held.append((route,params,body));return
        complete(route,params,body)
    def downstream(route):
        uploads.append({'body':route.request.post_data_buffer.decode(),'transport':route.request.resource_type})
        route.fulfill(status=200,content_type='application/json',body='{"ok":true}')
    page.route(ORIGIN+'/api/qx-privacy/prepare?*',prepare)
    page.route(ORIGIN+'/api/session/uploadFileBinary?*',downstream)
    page.route(ORIGIN+'/api/qx-knowledge/upload?*',downstream)
    page.route(ORIGIN+'/',lambda route:route.fulfill(content_type='text/html',body=HTML))
    page.goto(ORIGIN+'/');page.add_script_tag(path=str(ROOT/'plugins/privacy/client.js'))
    card,library=page.locator('[data-composer-card]'),page.locator('.qx-kb')
    check,mode=card.locator('input[type=checkbox]'),card.get_by_role('combobox',name='脱敏方式')
    def file(body='PRIVATE',name='synthetic.txt'):return {'name':name,'mimeType':'text/plain','buffer':body.encode()}
    def count():return page.evaluate('received.length')
    def wait(n):page.wait_for_function('(n)=>received.length===n',arg=n)
    def settle():expect(card.locator('.qx-privacy')).to_have_attribute('data-busy','false')
    def release():complete(*held.pop(0))
    def drag(kind,target,body='PRIVATE'):
        target.evaluate('''(el,d)=>{const dt=new DataTransfer();dt.items.add(new File([d.body],'synthetic.png',{type:'image/png'}));el.dispatchEvent(d.kind==='paste'?new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:dt}):new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}));}''',{'kind':kind,'body':body})
    expect(check).not_to_be_checked();expect(mode).to_be_hidden()
    card.locator('#chatfiles').set_input_files(file('UNCHANGED'));wait(1)
    assert page.evaluate('received[0].text')=='UNCHANGED' and not calls
    check.check();expect(mode).to_have_value('standard')
    card.locator('#chatfiles').set_input_files(file());wait(2);assert calls[-1]['mode']=='standard'
    mode.select_option('deep');card.locator('summary').click()
    expect(card.locator('[data-mode-hint]')).to_contain_text('资质、荣誉与覆盖规模')
    card.locator('#chatfiles').set_input_files(file());wait(3);assert calls[-1]['mode']=='deep'
    checks.append('default off, standard/deep picker and explanation')
    for kind,target in [('paste',card.locator('[contenteditable]')),('drop',page.locator('body'))]:
        n=count()+1;drag(kind,target);wait(n);assert calls[-1]['mode']=='deep'
    checks.append('clipboard screenshot and whole-document OS drop')
    mode.select_option('standard');card.locator('textarea').fill('FIRST TERM');n=count()+2;start=len(calls)
    card.locator('#chatfiles').set_input_files([file('HOLD SNAPSHOT','first.txt'),file('SECOND','second.txt')])
    expect(card.locator('.qx-privacy')).to_have_attribute('data-busy','true')
    card.get_by_role('button',name='发送',exact=True).click();assert page.evaluate('sent')==0
    mode.select_option('deep');card.locator('textarea').fill('NEW TERM');assert held;release();wait(n);settle()
    assert len(calls)==start+2 and [c['mode'] for c in calls[start:]]==['standard','standard']
    assert all(c['terms']==['FIRST TERM'] for c in calls[start:]) and len({c['context'] for c in calls[start:]})==1
    checks.append('whole-batch mode/terms/context snapshot; pending send held')
    start=len(calls);n=count()+2;mode.select_option('standard')
    card.locator('#chatfiles').set_input_files(file('HOLD CONCURRENT'))
    expect(card.locator('.qx-privacy')).to_have_attribute('data-busy','true')
    mode.select_option('deep');card.locator('#chatfiles').set_input_files(file('PARALLEL'));wait(n-1)
    assert held;release();wait(n);settle();assert [c['mode'] for c in calls[start:]]==['standard','deep']
    checks.append('concurrent batches keep independent modes')
    for body in ['FAIL','MISSING_MODE','WRONG_MODE','NETWORK']:
        n=count();card.locator('#chatfiles').set_input_files(file(body))
        expect(card.locator('[role=status]')).to_contain_text('原件未发送');settle();assert count()==n
    n=count();card.locator('#chatfiles').set_input_files([file('FIRST OK'),file('FAIL')])
    expect(card.locator('[role=status]')).to_contain_text('原件未发送');settle();assert count()==n
    checks.append('failure/network/missing-mode/wrong-mode/partial-batch never release raw bytes')
    library.locator('input[type=checkbox]').check();km=library.get_by_role('combobox',name='脱敏方式')
    expect(km).to_have_value('standard');expect(mode).to_have_value('deep')
    n=count();library.locator('#knowledge').set_input_files(file());wait(n+1)
    kc=calls[-1]['context'];assert calls[-1]['mode']=='standard';km.select_option('deep')
    n=count();drag('paste',library);wait(n+1);assert calls[-1]['mode']=='deep' and calls[-1]['context']!=kc
    n=count();drag('drop',library);wait(n+1)
    n=count();library.locator('#restore').set_input_files(file('BACKUP','backup.zip'));wait(n+1)
    assert page.evaluate('received.at(-1).text')=='BACKUP'
    checks.append('knowledge independent mode/context, picker/paste/drop, local ZIP bypass')
    n=count();card.locator('#chatfiles').set_input_files(file('HOLD SWITCH'))
    expect(card.locator('.qx-privacy')).to_have_attribute('data-busy','true')
    page.evaluate("document.documentElement.dataset.qxSessionId='synthetic-second-session'")
    expect(check).not_to_be_checked();assert held;release();page.wait_for_timeout(100);assert count()==n
    check.check();mode.select_option('deep');page.evaluate('delete document.documentElement.dataset.qxSessionId')
    expect(mode).to_have_value('deep');settle();checks.append('session switch refuses old-batch replay')
    protected=[u for u in uploads if u['body']!='UNCHANGED']
    assert protected and all('姓名：【人物1】' in u['body'] for u in protected)
    assert {'xhr','fetch'}<={u['transport'] for u in uploads}
    checks.append('downstream chat XHR and knowledge fetch carry safe File bytes')
    mode.select_option('standard');mode.select_option('deep');card.locator('textarea').fill('示例姓名（可选）')
    km.select_option('standard');library.locator('summary').click()
    card.locator('#received').evaluate('(el)=>el.textContent="已添加：深度脱敏文字副本.txt"')
    for width in [1000,420,320]:
        page.set_viewport_size({'width':width,'height':1100});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(OUT/f'privacy-{width}.png'),full_page=True)
    checks.append('1000/420/320 layouts have no horizontal overflow')
    n=count();card.locator('#chatfiles').set_input_files(file('HOLD ABORT'))
    expect(card.locator('.qx-privacy')).to_have_attribute('data-busy','true')
    page.evaluate('window.qxPrivacy.dispose()');assert page.locator('.qx-privacy').count()==0 and count()==n
    for pending,_,_ in held:pending.abort('aborted')
    held.clear()
    checks.append('dispose aborts pending conversion and removes controls');assert not errors,errors
    browser.close()
    report={'passed':True,'checks':checks,'prepare_requests':len(calls),'safe_downstream_uploads':len(protected),
            'models_called':0,'customer_sessions_read':0,'scope':'Isolated UI with mocked privacy responses; downstream XHR/fetch after captured UI intake. Arbitrary direct network calls are outside this event-hook boundary.',
            'parameters':calls,'transport_types':sorted({u['transport'] for u in uploads}),'page_errors':errors}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(str(OUT))
