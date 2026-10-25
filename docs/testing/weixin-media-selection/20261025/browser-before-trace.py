"""Disposable native synthetic Weixin-to-task media selection; no real channel/model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
from threading import Thread
import time
from uuid import uuid4

from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.config import load_settings
from cn_contract.ops import backup
from cn_contract.persistence import Database
from cn_contract.review.synthetic import select_fixture
from cn_contract.security import authenticate, login
from cn_contract.task_drafts import service as tasks
from cn_contract.web.app import create_app
from cn_contract.web.local_server import initialize_workspace
from cn_contract.weixin_inbox import accounts, generation_dispatch, generation_ingress, generations


def seed(database, actor):
    with database.session() as db:
        root = conversations.create_conversation(actor, d.AssistantConversationCreateInput(
            request_id=uuid4(), display_title='独立合成微信入口'), db)
        root_binding = tasks.create_binding(actor, root.scope.conversation_id, db)
    account = accounts.create_synthetic_account(actor, d.WeixinAccountCreateInput(
        bot_account_id='synthetic-browser-media-bot'), database=database)
    mapping = accounts.bind_synthetic_peer(actor, account.id, d.WeixinPeerBindInput(
        sender_peer_id='synthetic-browser-media-peer', task_binding_id=root_binding.id,
        expected_scope=root.scope), database=database)
    previous = None
    result = []
    for ordinal, kind in enumerate(('docx','pdf'), 1):
        with database.session() as db:
            target = conversations.create_conversation(actor, d.AssistantConversationCreateInput(
                request_id=uuid4(), display_title='合成待收件原件关联 '+kind.upper()), db)
            binding = tasks.create_binding(actor, target.scope.conversation_id, db)
        current = accounts.read_synthetic_account(actor, account.id, database=database)
        value = d.WeixinPeerGenerationInput(request_id=uuid4(), expected_generation=ordinal-1,
            expected_previous_generation_sha256=previous.generation_sha256 if previous else None,
            expected_previous_scope_sha256=previous.scope_sha256 if previous else mapping.scope_sha256,
            expected_checkpoint_revision=current.checkpoint_revision, task_binding_id=binding.id,
            expected_scope=target.scope, reason='独立合成浏览器原件关联验收')
        previous = generations.append_synthetic_generation(actor, mapping.id, value, database=database)
        message = dict(message_id=ordinal, from_user_id=mapping.sender_peer_id,
            to_user_id=account.bot_account_id, message_type=1, message_state=2,
            item_list=[{'type':1,'text_item':{'text':'帮我审查合同，核对独立合成材料。'}},
                       {'type':4,'file_item':{'file_name':'收件待核主合同.'+kind}}])
        raw = json.dumps({'ret':0,'msgs':[message],'get_updates_buf':'synthetic-media:'+str(ordinal)},
                         ensure_ascii=False).encode('utf-8')
        receipt = generation_ingress.record_generation_poll(actor, account.id,
            d.WeixinPollInput(request_id=uuid4(), expected_revision=current.checkpoint_revision,
                expected_cursor=current.upstream_cursor), raw, database=database)
        delivery = generation_dispatch.dispatch_generation_descriptor(actor, receipt.descriptors[0].id, database=database)
        with database.session() as db:
            draft = tasks.list_drafts(actor, target.scope.conversation_id, db).items[0]
        assert draft.events[0].media[0].attachment_id is None and 'media_pending' in draft.blockers
        result.append(dict(kind=kind,cid=str(target.scope.conversation_id),draft_id=str(draft.id),
                           event_id=str(delivery.task_event_id),media_id=draft.events[0].media[0].media_id))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    root = output/'独立合成工作区'
    username, password = 'synthetic','Test-4271'
    initialize_workspace(root,username,password,data_parent=output)
    settings = load_settings()
    database = Database('sqlite:///'+str(root/'workbench.db'),root/'protected',settings,initialize_schema=False)
    backup._mark_storage_flags(database)
    _, _, registered_docx, _ = select_fixture('sales')
    sources = {'docx':registered_docx,
               'pdf':repo/'tests/fixtures/task-pdf-v1/native-sales.pdf'}
    source_hashes = {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items()}
    with database.session() as db:
        token,_ = login(username,password,db)
        actor = authenticate(token,db)
    cases = seed(database,actor)
    with database.session() as db:
        originals = [tuple(row) for row in db.execute(text('SELECT * FROM task_inbox_events ORDER BY rowid'))]
    app = create_app(settings,database=database,assistant_home_enabled=True,purpose='mock_demo')
    import uvicorn
    listener = socket.socket();listener.bind(('127.0.0.1',0))
    base = 'http://127.0.0.1:'+str(listener.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
    thread = Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
    thread.start()
    deadline=time.monotonic()+15
    while not server.started and time.monotonic()<deadline: time.sleep(.05)
    assert server.started
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(repo/'.local/scrapling/browsers'))
    from playwright.sync_api import sync_playwright, expect
    report = dict(scope='disposable native synthetic services + real loopback FastAPI/Chromium; installed Electron NOT_RUN',
                  steps=[],visual=[],external_requests=[],page_errors=[],source_sha256=source_hashes)
    try:
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':1280,'height':1000})
            def local_only(route):
                if route.request.url.startswith(base+'/'): route.continue_()
                else:
                    report['external_requests'].append(route.request.url);route.abort()
            context.route('**/*',local_only)
            response=context.request.post(base+'/api/login',data={'username':username,'password':password})
            assert response.status==200
            page=context.new_page()
            page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            for case in cases:
                kind=case['kind'];cid=case['cid']
                page.goto(base+'/assistant/'+cid+'#task-'+case['draft_id'])
                page.get_by_role('button',name='审查合同 · 模拟',exact=True).first.click()
                expect(page.locator('#task-select')).to_have_value(case['draft_id'])
                def show_record():
                    details=page.locator('#task-current details').first
                    if details.get_attribute('open') is None: details.locator('summary').click()
                    return details.locator('.task-media-row').first
                row=show_record()
                expect(row.locator('select')).to_have_value('')
                expect(row.get_by_role('button',name='关联所选原件并更新读取状态',exact=True)).to_be_disabled()
                expect(page.get_by_role('button',name='冻结材料',exact=True)).to_be_disabled()
                page.locator('#add-material').click()
                name='独立合成采购主合同_用于核对收件与本机原件关联及中文窄窗口测试_版本一.'+kind
                mime='application/pdf' if kind=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                page.locator('#material-file').set_input_files({'name':name,'mimeType':mime,'buffer':sources[kind].read_bytes()})
                page.locator('#material-consent').check()
                page.locator('#upload-material').click()
                expect(page.locator('#material-list')).to_contain_text(name)
                page.get_by_role('button',name='核对原文',exact=True).click()
                page.get_by_role('button',name='读取 '+kind.upper(),exact=True).click()
                expect(page.locator('#material-preview')).to_contain_text('已读取，内容仍待核实')
                page.locator('#close-material-preview').click()
                row=show_record();select=row.locator('select')
                expect(select).to_have_value('')
                assert select.locator('option').count()==2
                assert select.evaluate('el=>el.labels.length')==1
                select.focus();select.press('ArrowDown');select.press('Enter')
                attachment_id=select.input_value();assert attachment_id
                confirm=row.get_by_role('button',name='关联所选原件并更新读取状态',exact=True)
                expect(confirm).to_be_enabled()
                if kind=='docx':
                    for width in (1280,360):
                        page.set_viewport_size({'width':width,'height':1000})
                        confirm.scroll_into_view_if_needed();confirm.focus()
                        check=page.evaluate('''()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                          focus:document.activeElement.textContent,font:getComputedStyle(document.body).fontFamily})''')
                        assert check['scrollWidth']<=check['width'],check
                        report['visual'].append(check)
                        page.screenshot(path=str(output/('selection-'+str(width)+'.png')),full_page=True)
                    page.set_viewport_size({'width':1280,'height':1000})
                writes=[];lost=[False]
                def lose_ack(route):
                    if route.request.method=='PATCH':
                        writes.append(route.request.method)
                        if kind=='pdf' and not lost[0]:
                            committed=route.fetch();assert committed.status==200
                            lost[0]=True;route.abort('failed');return
                    route.continue_()
                page.route('**/api/task-drafts/'+case['draft_id'],lose_ack)
                confirm.focus();confirm.press('Enter')
                if kind=='pdf':
                    retry=page.get_by_role('button',name='查询本次关联结果',exact=True)
                    expect(retry).to_be_visible()
                    expect(page.locator('#task-notice')).to_contain_text('尚未确认')
                    retry.click()
                expect(page.locator('#task-current')).to_contain_text('读取就绪')
                expect(page.get_by_role('button',name='冻结材料',exact=True)).to_be_enabled()
                assert writes==['PATCH']
                page.unroute('**/api/task-drafts/'+case['draft_id'],lose_ack)
                with database.session() as db:
                    draft=tasks.read_draft(actor,case['draft_id'],db)
                    assert len(draft.media_resolutions)==1
                    resolution=draft.media_resolutions[0]
                    assert str(resolution.replacement.attachment_id)==attachment_id
                    assert resolution.media_id==case['media_id'] and resolution.replacement.status=='ready'
                    assert draft.events[0].media[0].attachment_id is None
                    assert [tuple(row) for row in db.execute(text('SELECT * FROM task_inbox_events ORDER BY rowid'))]==originals
                    backup._file_references(db)
                report['steps'].append(dict(kind=kind,explicit_choice=True,keyboard_confirm=True,
                    patch_count=len(writes),lost_ack_query_only=lost[0],original_event_preserved=True))
                page.reload()
                page.get_by_role('button',name='审查合同 · 模拟',exact=True).first.click()
                page.locator('#task-select').select_option(case['draft_id'])
                show_record()
                expect(page.locator('#task-current')).to_contain_text('读取就绪')
            browser.close()
        with database.session() as db:
            report['counts']={name:db.scalar(text('SELECT count(*) FROM '+name)) for name in
                ('weixin_peer_generations','weixin_dispatch_receipts','task_media_resolutions',
                 'task_executions','assistant_runs','assistant_model_attempts','review_runs')}
        assert all(report['counts'][name]==0 for name in ('task_executions','assistant_runs','assistant_model_attempts','review_runs'))
        assert report['counts']['task_media_resolutions']==2
        assert {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items()}==source_hashes
        assert not report['external_requests'] and not report['page_errors']
        report['status']='PASS'
    except BaseException as error:
        report['status']='FAIL';report['error']=str(error)
        raise
    finally:
        server.should_exit=True;thread.join(timeout=10);database.engine.dispose()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
