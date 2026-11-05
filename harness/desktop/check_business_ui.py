"""Synthetic business conversations on the isolated Harness host; no real model or messages."""
import json,time,subprocess,os,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.environ.get('QX_QA_DATA',ROOT/'.local/business-workflows-qa/data'))
OUT=ROOT/'docs/checks/business-workflows';OUT.mkdir(parents=True,exist_ok=True)
runtime=json.loads((DATA/'.local/runtime.json').read_text(encoding='utf-8'))
report={'status':'running','errors':[],'checks':[],'model':'loopback fixture only'}
started=time.time()
NODE='C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
paths=json.loads(subprocess.check_output([NODE,'-e',"const {createRequire}=require('module');const dsh=createRequire(require.resolve('@deepseek-ai/dsh/package.json'));const web=createRequire(dsh.resolve('@deepseek-ai/dsh-web-app/package.json'));process.stdout.write(JSON.stringify(Object.fromEntries(['workspace','chat'].map(x=>[x,web.resolve('@deepseek-ai/dsh-client-ui-'+x+'/client')]))));"],cwd=ROOT,text=True))
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN',permissions=['clipboard-read','clipboard-write'])
    context.add_init_script("window.__DSH_LOCALE__={read:async()=>({languages:['zh-CN'],preference:'zh'}),onChange:()=>{}}")
    context.route('**/api/qx-account/balance*',lambda r:r.fulfill(json={'status':'unavailable','balances':[]}))
    def bundle(route):
        response=route.fetch();body=response.text().replace('\r\n','\n')
        for package in ['workspace','chat']:
            if 'id: "@deepseek-ai/dsh-client-ui-'+package+'"' in body:
                replacement=Path(paths[package]).read_text(encoding='utf-8').rstrip()
                target=body.index('id: "@deepseek-ai/dsh-client-ui-'+package+'"')
                start=body.rfind('window.__ModuleLoader__.load(',0,target)
                end=body.find('\nwindow.__ModuleLoader__.load(',target)
                if end<0:end=len(body)
                assert start>=0
                count=body.count('window.__ModuleLoader__.load(')
                body=body[:start]+replacement+'\n'+body[end:]
                assert body.count('window.__ModuleLoader__.load(')==count
                report['nativeExtension_'+package]=True
        if "id:'@qunxing/desktop-session'" in body:
            report['currentBundle']='guided business conversations' in body
            marker="return {inject:['sessions','uiWorkspace','slots','sidebarRight'],apply(ctx){"
            assert marker in body
            body=body.replace(marker,marker+'window.__qxTest=ctx;')
            route.fulfill(response=response,body=body)
        else:route.fulfill(response=response,body=body)
    context.route('**/*.js*',bundle)
    page=context.new_page()
    def page_error(error):report['errors'].append(str(error));print('PAGE ERROR:',str(error),flush=True)
    page.on('pageerror',page_error)
    page.on('console',lambda message:print('CONSOLE ERROR:',message.text[:1500],flush=True) if message.type=='error' else None)
    def current():return page.locator('[data-conversation-content]').get_attribute('data-conversation-session')
    def editor():return page.locator('[data-conversation-content] [contenteditable=true][role=textbox]').first
    def check(name):report['checks'].append(name);print(name,flush=True)
    try:
        page.goto(runtime['url'],wait_until='domcontentloaded')
        try:page.get_by_role('button',name='开始使用',exact=True).click(timeout=7000)
        except Exception:pass
        entries=page.get_by_role('region',name='四大业务入口')
        expect(entries).to_be_visible(timeout=60000)
        assert report['currentBundle'],'Source integration client was not loaded'
        page.screenshot(path=str(OUT/'entries.png'))
        for title in ['客户接待','合同审查','办案整理','模拟法庭']:expect(entries.get_by_role('button',name='新建'+title+'对话',exact=True)).to_be_visible()
        check('左侧四业务入口与原生工作区同时显示')
        for title in ['客户接待','合同审查','办案整理','模拟法庭']:
            entries.get_by_role('button',name='新建'+title+'对话',exact=True).click()
            expect(page.get_by_role('region',name=title+'业务引导')).to_be_visible(timeout=30000)
            business=current();editor().fill('保留业务草稿：'+title)
            page.get_by_text('新会话',exact=True).first.click()
            page.wait_for_function('old=>document.querySelector("[data-conversation-content]")?.dataset.conversationSession!==old',arg=business)
            expect(page.locator('.qx-business-dock')).to_have_count(0,timeout=15000)
            expect(editor()).to_be_empty()
            page.evaluate('id=>window.__qxTest.uiWorkspace.openSession(id)',business)
            expect(page.get_by_role('region',name=title+'业务引导')).to_be_visible()
            expect(editor()).to_have_text('保留业务草稿：'+title);editor().fill('')
        check('四业务后原生新建进入普通空白对话；返回业务仍保留引导与草稿')
        entries.get_by_role('button',name='新建合同审查对话',exact=True).click()
        dock=page.get_by_role('region',name='合同审查业务引导');expect(dock).to_be_visible(timeout=30000)
        contract=current();editor().fill('待补充合同的合成草稿')
        entries.get_by_role('button',name='新建合同审查对话',exact=True).click()
        assert current()==contract;expect(editor()).to_have_text('待补充合同的合成草稿')
        entries.get_by_role('button',name='新建客户接待对话',exact=True).click()
        expect(page.get_by_role('region',name='客户接待业务引导')).to_be_visible(timeout=30000)
        reception=current();assert reception!=contract;expect(editor()).to_be_empty()
        page.evaluate('id=>window.__qxTest.uiWorkspace.openSession(id)',contract)
        expect(editor()).to_have_text('待补充合同的合成草稿')
        check('新建业务对话不覆盖旧草稿；重复点击当前空对话不会重复创建')
        editor().fill('')
        contract_file=DATA/'合成合同.txt';contract_file.write_text('合成合同：甲方测试甲公司，乙方测试乙公司，服务费用为 100 元。',encoding='utf-8')
        page.locator('[data-conversation-content] input[type=file]').first.set_input_files(str(contract_file))
        send_button=page.get_by_role('button',name='发送消息',exact=True);expect(send_button).to_be_enabled(timeout=30000);send_button.click()
        expect(dock.get_by_role('button',name='甲方',exact=True)).to_be_visible(timeout=30000)
        expect(page.get_by_text('已收到合同。甲方为测试甲公司',exact=False).first).to_be_visible(timeout=60000)
        dock.get_by_role('button',name='乙方',exact=True).click()
        expect(dock.get_by_role('button',name='全面审查（推荐）',exact=True)).to_have_attribute('aria-pressed','true')
        dock.get_by_role('button',name='重点审查',exact=True).click()
        expect(dock.get_by_role('button',name='开始审查',exact=True)).to_be_disabled()
        dock.get_by_role('textbox',name='重点审查事项',exact=True).fill('付款和解除条件')
        dock.get_by_role('button',name='开始审查',exact=True).click()
        expect(dock).to_contain_text('我方：乙方 · 重点审查',timeout=30000)
        expect(page.get_by_text('已按您确认的选项开始处理',exact=False).first).to_be_visible(timeout=60000)
        check('只上传合同无需提示词；先立场再程度，重点审查须补充关注事项')
        page.screenshot(path=str(OUT/'contract.png'))
        page.evaluate('id=>window.__qxTest.uiWorkspace.openSession(id)',reception)
        rdock=page.get_by_role('region',name='客户接待业务引导');expect(rdock).to_be_visible(timeout=30000)
        editor().fill('客户说：我有一份合同纠纷，想先咨询一下。');editor().press('Enter')
        reply=page.get_by_role('region',name='客户接待回复').last
        expect(reply.get_by_role('button',name='复制回复',exact=True)).to_be_visible(timeout=60000)
        assert reply.locator('details').get_attribute('open') is None
        reply.get_by_role('button',name='复制回复',exact=True).click()
        copied=page.evaluate('navigator.clipboard.readText()');assert '您好' in copied and '待核实' not in copied
        check('接待可复制客户回复，内部参考默认折叠且不进入复制内容')
        editor().fill('合成草稿不得覆盖');reply.get_by_role('button',name='更简短',exact=True).click()
        expect(editor()).to_have_text('合成草稿不得覆盖');expect(reply).to_contain_text('请先发送或保存输入框中的内容')
        editor().fill('');reply.get_by_role('button',name='推进预约',exact=True).click()
        expect(page.get_by_role('region',name='客户接待回复')).to_have_count(2,timeout=60000)
        check('推进预约自动提交简短操作，已有草稿时阻止覆盖')
        rdock.get_by_role('combobox',name='接待阶段').select_option('engaged')
        expect(rdock.get_by_role('combobox',name='接待阶段')).to_have_value('new')
        rdock.get_by_role('button',name='确认已委托',exact=True).click()
        expect(rdock.get_by_role('combobox',name='接待阶段')).to_have_value('engaged')
        check('标记已委托必须二次明确确认')
        rdock.get_by_role('button',name='转入办案',exact=True).click()
        rdock.get_by_role('textbox',name='办案交接摘要',exact=True).fill('本摘要仅属于接待 A')
        rdock.get_by_role('checkbox').check()
        entries.get_by_role('button',name='新建客户接待对话',exact=True).click()
        expect(rdock.get_by_role('combobox',name='接待阶段')).to_have_value('new',timeout=30000)
        expect(rdock.get_by_role('textbox',name='办案交接摘要',exact=True)).to_have_count(0)
        page.evaluate('id=>window.__qxTest.uiWorkspace.openSession(id)',reception)
        expect(rdock.get_by_role('combobox',name='接待阶段')).to_have_value('engaged',timeout=30000)
        check('切换接待会话不会继承其他客户的摘要、确认勾选或阶段')
        rdock.get_by_role('button',name='转入办案',exact=True).click()
        rdock.get_by_role('textbox',name='办案交接摘要',exact=True).fill('已确认：测试客户希望核对服务合同付款条款；尚未收到付款凭证。')
        expect(rdock.get_by_role('button',name='确认并新建办案对话',exact=True)).to_be_disabled()
        rdock.get_by_role('checkbox').check();rdock.get_by_role('button',name='确认并新建办案对话',exact=True).click()
        cdock=page.get_by_role('region',name='办案整理业务引导');expect(cdock).to_be_visible(timeout=30000)
        case=current();cdock.locator('summary').click();expect(cdock).to_contain_text('尚未收到付款凭证')
        expect(editor()).to_be_empty();check('转办案仅携带人工核对确认的摘要')
        page.reload(wait_until='domcontentloaded');page.wait_for_function('id=>window.__qxTest?.sessions.list.getSnapshot().byId[id]',arg=reception,timeout=30000)
        page.evaluate('id=>window.__qxTest.uiWorkspace.openSession(id)',reception)
        expect(page.get_by_role('region',name='客户接待业务引导').get_by_role('combobox',name='接待阶段')).to_have_value('engaged',timeout=30000)
        entries.get_by_role('button',name='客户接待历史对话',exact=True).click();expect(page.locator('.qx-business-history button').first).to_be_visible()
        check('刷新后业务类型、阶段和分类历史保留')
        page.screenshot(path=str(OUT/'reception.png'))
        for title in ['模拟法庭','办案整理']:
            entries.get_by_role('button',name='新建'+title+'对话',exact=True).click()
            expect(page.get_by_role('region',name=title+'业务引导')).to_be_visible(timeout=30000)
            expect(editor()).to_be_empty()
        check('模拟法庭和办案整理均可创建独立业务对话')
        page.evaluate('id=>window.__qxTest.uiWorkspace.openSession(id)',reception)
        expect(rdock).to_be_visible(timeout=30000)
        page.set_viewport_size({'width':900,'height':720});page.screenshot(path=str(OUT/'compact.png'))
        assert page.locator('.qx-business-dock').evaluate('e=>e.scrollWidth<=e.clientWidth')
        check('紧凑窗口引导无横向溢出')
        systems=[json.loads(file.read_text(encoding='utf-8'))['workflow'] for file in DATA.glob('mock-*.json') if file.stat().st_mtime>=started]
        assert any('不得开始正式审查' in system for system in systems)
        assert any('可以正式审查' in system and '乙方' in system and '付款和解除条件' in system for system in systems)
        assert any('推进咨询和委托' in system for system in systems)
        check('实际模型请求已收到各会话业务指引与最新确认选项')
        assert not report['errors'],report['errors'];report['status']='passed'
    except Exception as error:
        try:
            report['slots']=page.evaluate("""()=>['sidebar.workspaces','conversation.chat.node'].map(name=>({name,entries:window.__qxTest?.slots.entriesOfSlot(name).map(e=>({keys:Object.keys(e),options:e.options,hasComponent:!!e.component}))}))""")
        except Exception:pass
        report.update(status='failed',error=str(error));page.screenshot(path=str(OUT/'failure.png'))
        (OUT/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8');raise
    finally:
        (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
