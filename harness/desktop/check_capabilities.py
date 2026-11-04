"""Isolated actual installed UI and synthetic drafts; never sends a prompt."""
import json, sys, time, uuid
from pathlib import Path
from urllib.parse import urlparse
sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parents[1]
out=root/'desktop/checks'/(time.strftime('%Y%m%d-%H%M%S')+'-capabilities')
out.mkdir(parents=True)
runtime=json.loads(Path('C:/Users/Lenovo/AppData/Roaming/QunxingHarness/.local/runtime.json').read_text(encoding='utf-8-sig'))
report={'status':'running','scope':'Isolated installed UI; synthetic unsent drafts; no model or WeChat actions','errors':[],'sent':0}
report['installedBundle']=True
session_id=None
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
    context.add_init_script("window.__DSH_LOCALE__={read:async()=>({languages:['zh-CN'],preference:'zh'}),onChange:()=>{}}")
    def bundle(route):
        response=route.fetch()
        body=response.text()
        if "id:'@qunxing/desktop-session'" in body:
            report['bundle']=urlparse(route.request.url).path
            source=body
            assert 'qx-capability-grid' in source, 'Installed bundle is stale'
            marker="return {inject:['sessions','uiWorkspace','slots'],apply(ctx){"
            route.fulfill(response=response,body=source.replace(marker,marker+'window.__qxTest=ctx;'))
        else: route.fulfill(response=response)
    context.route('**/*.js*',bundle)
    context.route('**/qx-wechat/state',lambda r:r.fulfill(json={'sessionId':None,'connected':False}))
    context.route('**/api/qx-account/balance*',lambda r:r.fulfill(json={'status':'ok','balances':[{'currency':'CNY','total_balance':'123.45'}]}))
    def no_send(route):
        report['sent']+=1
        route.abort()
    context.route('**/api/session/prompt',no_send)
    context.route('**/qx-wechat/action',no_send)
    page=context.new_page()
    page.on('pageerror',lambda e:report['errors'].append(str(e)))
    try:
        page.goto(runtime['url'],wait_until='domcontentloaded')
        try:
            page.get_by_role('button',name='开始使用',exact=True).wait_for(timeout=7000)
            expect(page.get_by_text('欢迎使用AI师兄法律助手平台',exact=True)).to_be_visible()
            report['welcomeName']=True
            page.get_by_role('button',name='开始使用',exact=True).click()
        except Exception: pass
        page.wait_for_function('window.__qxTest?.uiWorkspace',timeout=40000)
        session_id='qx-capabilities-test-'+str(uuid.uuid4())
        created=page.evaluate("""async id=>{async function rpc(method,request){const r=await fetch('/api/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:crypto.randomUUID(),method,payload:{args:{request}}})});const result=(await r.json()).result;if(!result?.ok)throw Error(method+' failed');return result.value;}const {workspace}=await rpc('workspace/create',{path:'C:/Users/Lenovo/AppData/Roaming/QunxingHarness/workspace'});await rpc('session/create',{sessionId:id,workspaceId:workspace.workspaceId,agentPreset:'qunxing'});return true;}""",session_id)
        assert created, 'Synthetic session creation failed'
        page.evaluate('id=>window.__qxTest.uiWorkspace.openSession(id)',session_id)
        cards=page.get_by_role('region',name='四大法律服务能力')
        expect(cards).to_be_visible(timeout=30000)
        expect(cards.get_by_role('button')).to_have_count(4)
        expect(page.locator('.qx-wordmark')).to_have_text('AI师兄法律助手平台')
        expect(page.locator('[data-conversation-content]').get_by_text('AI师兄法律助手平台',exact=True)).to_be_visible()
        report['brandName']=True
        expect(page.locator('[data-conversation-content]')).to_have_attribute('data-conversation-session',session_id)
        editor=page.locator('[data-conversation-content] [contenteditable="true"][role="textbox"]')
        page.screenshot(path=str(out/'desktop.png'))
        for title,phrase in [('客户接待','请协助我接待一位客户'),('合同审查','请审查我提供的合同'),('办案整理','请根据我提供的案件材料'),('模拟法庭','请围绕我提供的案件开展模拟法庭演练')]:
            editor.fill('')
            cards.get_by_role('button',name=title+'：填入提示词',exact=True).click()
            expect(editor).to_contain_text(phrase)
            expect(editor).to_be_focused()
        editor.fill('这是合成草稿，请保留。')
        editor.press('Control+a')
        cards.get_by_role('button',name='合同审查：填入提示词',exact=True).click()
        expect(editor).to_contain_text('这是合成草稿，请保留。')
        expect(editor).to_contain_text('请审查我提供的合同')
        draft=editor.inner_text()
        cards.get_by_role('button',name='合同审查：填入提示词',exact=True).click()
        expect(editor).to_have_text(draft)
        editor.press('Control+z')
        expect(editor).to_have_text('这是合成草稿，请保留。')
        editor.fill('')
        first=cards.get_by_role('button').first
        first.hover()
        page.wait_for_timeout(600)
        assert first.evaluate("e=>parseFloat(getComputedStyle(e).transform.split('(')[1])>1")
        page.screenshot(path=str(out/'hover.png'))
        page.mouse.move(20,20)
        page.wait_for_timeout(650)
        assert first.evaluate("e=>getComputedStyle(e).transform==='matrix(1, 0, 0, 1, 0, 0)'")
        first.focus()
        first.press('Enter')
        expect(editor).to_contain_text('请协助我接待一位客户')
        page.reload(wait_until='domcontentloaded')
        page.wait_for_function('window.__qxTest?.uiWorkspace')
        page.wait_for_function('id=>window.__qxTest.sessions.list.getSnapshot().byId[id]',arg=session_id)
        page.evaluate('id=>window.__qxTest.uiWorkspace.openSession(id)',session_id)
        expect(editor).to_contain_text('请协助我接待一位客户')
        editor.fill('')
        for width,height in [(900,720),(600,800)]:
            page.set_viewport_size({'width':width,'height':height})
            expect(cards).to_be_visible()
            cards.scroll_into_view_if_needed()
            assert cards.evaluate('e=>e.scrollWidth<=e.clientWidth')
            page.screenshot(path=str(out/f'compact-{width}.png'))
        page.emulate_media(reduced_motion='reduce')
        first.hover()
        assert first.evaluate("e=>getComputedStyle(e).transform==='none'")
        assert report['sent']==0
        assert not report['errors'],report['errors']
        report.update(status='passed',checks=['四张能力卡片','四种提示词填入且焦点回输入框','保留选中草稿与撤销','重复点击不重复追加','悬停放大与离开回弹','键盘与减少动画','窄屏无横向溢出','无模型或微信请求'])
    except Exception as error:
        report.update(status='failed',error=str(error))
        page.screenshot(path=str(out/'failure.png'))
        raise
    finally:
        if session_id:
            try:
                report['archived']=page.evaluate("""async id=>{const method='workspace/archiveSession';const r=await fetch('/api/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:crypto.randomUUID(),method,payload:{args:{request:{sessionId:id,stopActivity:true}}}})});return (await r.json()).result?.ok===true}""",session_id)
            except Exception: report['archived']=False
        browser.close()
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':report['status'],'report':str(out/'report.json')},ensure_ascii=False))
