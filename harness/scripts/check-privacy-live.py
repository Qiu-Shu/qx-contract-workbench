"""Real authenticated Harness upload; synthetic files, no model or WeChat messages."""
import json
from pathlib import Path
import time
from uuid import uuid4
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.local/privacy-live-check'/time.strftime('%Y%m%d-%H%M%S')
OUT.mkdir(parents=True)
runtime=json.loads((ROOT/'.local/runtime.json').read_text(encoding='utf-8-sig'))
url=urlsplit(runtime['url']);origin=f'{url.scheme}://{url.netloc}'
report={'status':'running','model_requests':0,'wechat_messages':0,'uploads':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    context=browser.new_context(viewport={'width':1280,'height':850})
    context.request.get(runtime['url'])
    def rpc(method,args):
        result=context.request.post(origin+'/api/'+method,headers={'Origin':origin},data={'type':'client-request','rpcId':str(uuid4()),'method':method,'payload':{'args':{'request':args}}}).json()
        assert result['result']['ok'],method
        return result['result']['value']
    workspace_id=rpc('workspace/create',{'path':str(ROOT/'workspace')})['workspace']['workspaceId']
    session=rpc('session/create',{'sessionId':'qx-privacy-ui-'+str(uuid4()),'workspaceId':workspace_id,'agentPreset':'qunxing'})['sessionId']
    rpc('session/rename',{'sessionId':session,'title':'上传脱敏验证（虚构）'+OUT.name})
    report['sessionId']=session
    page=context.new_page()
    # Keep the isolated verifier on its own new session. The owner's WeChat binding is unchanged.
    page.route(origin+'/qx-wechat/state',lambda route:route.fulfill(content_type='application/json',body=json.dumps({'sessionId':session})))
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    def observed(request):
        if '/api/session/uploadFileBinary' in request.url:
            body=request.post_data_buffer or b''
            report['uploads'].append({'bytes':len(body),'contains_raw':any(s.encode() in body for s in ['张三','13800138000','zhang@example.com']),'plain_text':body.decode('utf-8',errors='replace')[:300]})
    context.on('request',observed)
    page.goto(origin,wait_until='domcontentloaded')
    try:
        page.wait_for_function('(id)=>document.documentElement.dataset.qxSessionId===id',arg=session,timeout=45000)
    except Exception:
        print(json.dumps({'errors':errors,'selected_test_session':page.evaluate('(id)=>document.documentElement.dataset.qxSessionId===id',session),'composer_count':page.locator('[data-composer-card]').count(),'privacy_controls':page.locator('.qx-privacy').count(),'test_session_label_count':page.get_by_text('上传脱敏验证（虚构）'+OUT.name,exact=True).count()},ensure_ascii=False))
        raise
    card=page.locator('[data-composer-card]')
    expect(card.locator('input[type=file]')).to_be_enabled(timeout=30000)
    check=card.locator('.qx-privacy input[type=checkbox]')
    expect(check).to_be_visible(timeout=30000);expect(check).not_to_be_checked();check.check()
    card.locator('details > summary').click();card.locator('.qx-privacy textarea').fill('张三')
    file={'name':'张三合同.txt','mimeType':'text/plain','buffer':'姓名：张三\n电话：13800138000\n邮箱：zhang@example.com\n合同总价10000元，2026年11月3日签订。'.encode()}
    try:
        with context.expect_event('response',predicate=lambda response:'/api/session/uploadFileBinary' in response.url,timeout=15000) as receipt:
            card.locator('input[type=file]').set_input_files(file)
        assert receipt.value.status==200
    except Exception:
        page.screenshot(path=str(OUT/'failure.png'))
        print(json.dumps({'composer':card.inner_text(),'errors':errors,'disabled':card.locator('input[type=file]').is_disabled()},ensure_ascii=False))
        raise
    expect(card.locator('.qx-privacy [role=status]')).to_contain_text('已生成 1 份',timeout=60000)
    page.wait_for_function('!!document.querySelector("[data-composer-card]")?.textContent.includes("脱敏文字")',timeout=45000)
    # Original upload receipts must never be created for the protected file.
    assert report['uploads'] and not any(item['contains_raw'] for item in report['uploads']),report
    assert any('10000' in item['plain_text'] for item in report['uploads'])
    for kind in ['drop','paste']:
        target=page.locator('body') if kind=='drop' else card.locator('[contenteditable=true]')
        with context.expect_event('response',predicate=lambda response:'/api/session/uploadFileBinary' in response.url,timeout=45000) as received:
            target.evaluate('''(el,kind)=>{const dt=new DataTransfer();dt.items.add(new File(['姓名：张三\\n电话：13800138000\\n应付10000元'],'模拟上传.txt',{type:'text/plain'}));el.dispatchEvent(kind==='paste'?new ClipboardEvent(kind,{bubbles:true,cancelable:true,clipboardData:dt}):new DragEvent(kind,{bubbles:true,cancelable:true,dataTransfer:dt}));}''',kind)
        assert received.value.status==200
    assert len(report['uploads'])==3 and not any(item['contains_raw'] for item in report['uploads'])
    card.locator('details > summary').click()
    page.screenshot(path=str(OUT/'desktop.png'))
    page.set_viewport_size({'width':720,'height':850});page.screenshot(path=str(OUT/'compact.png'))
    page.set_viewport_size({'width':1280,'height':850})
    page.get_by_role('button',name='律所知识库',exact=True).click()
    library=page.locator('.qx-kb');expect(library).to_be_visible()
    expect(library.locator('.qx-privacy')).to_have_count(1)
    library.locator('.qx-privacy input[type=checkbox]').check()
    library.locator('.qx-privacy summary').click();library.locator('.qx-privacy textarea').fill('张三')
    with context.expect_event('response',predicate=lambda response:'/api/qx-knowledge/upload' in response.url,timeout=45000) as registered:
        library.locator('input[type=file][multiple]').set_input_files(file)
    response=registered.value;assert response.status==201
    uploaded=response.request.post_data_buffer.decode('utf-8');assert all(value not in uploaded for value in ['张三','13800138000','zhang@example.com'])
    document=response.json();report['knowledge_upload']={'status':201,'raw_identifiers_absent':True,'document_id':document['id']}
    page.get_by_role('button',name='关闭知识库',exact=True).click()
    report.update(status='passed',page_errors=errors)
    assert not errors,errors
    browser.close()
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(str(OUT))
