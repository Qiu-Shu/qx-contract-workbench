"""Disposable synthetic browser verification; loopback only, no models or real data."""
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
from cn_contract.security import authenticate, login
from cn_contract.task_drafts import service as tasks
from cn_contract.web.app import create_app
from cn_contract.web.local_server import initialize_workspace
from cn_contract.weixin_inbox import accounts, generation_ingress, generations


def seed(database, actor):
    with database.session() as db:
        root = conversations.create_conversation(actor, d.AssistantConversationCreateInput(
            request_id=uuid4(), display_title='独立合成待收件入口'), db)
        root_binding = tasks.create_binding(actor, root.scope.conversation_id, db)
    account = accounts.create_synthetic_account(actor, d.WeixinAccountCreateInput(
        bot_account_id='synthetic-browser-pending-bot'), database=database)
    mapping = accounts.bind_synthetic_peer(actor, account.id, d.WeixinPeerBindInput(
        sender_peer_id='synthetic-browser-pending-peer',task_binding_id=root_binding.id,expected_scope=root.scope),database=database)
    previous = None
    targets = []
    for ordinal, count in ((1,21),(2,1)):
        with database.session() as db:
            target = conversations.create_conversation(actor, d.AssistantConversationCreateInput(
                request_id=uuid4(),display_title=f'合成历史目标{ordinal}：核对材料与付款'),db)
            binding = tasks.create_binding(actor,target.scope.conversation_id,db)
        current = accounts.read_synthetic_account(actor,account.id,database=database)
        previous = generations.append_synthetic_generation(actor,mapping.id,d.WeixinPeerGenerationInput(
            request_id=uuid4(),expected_generation=ordinal-1,
            expected_previous_generation_sha256=previous.generation_sha256 if previous else None,
            expected_previous_scope_sha256=previous.scope_sha256 if previous else mapping.scope_sha256,
            expected_checkpoint_revision=current.checkpoint_revision,task_binding_id=binding.id,expected_scope=target.scope,
            reason='独立合成待收件UI验收'),database=database)
        messages = [dict(message_id=ordinal*100+n,from_user_id=mapping.sender_peer_id,to_user_id=account.bot_account_id,
            message_type=1,message_state=2,item_list=[{'type':1,'text_item':{'text':'审查独立合成合同，正文不得出现在待收件列表。'}}]) for n in range(count)]
        wire = json.dumps({'ret':0,'msgs':messages,'get_updates_buf':'synthetic-pending:'+str(ordinal)},ensure_ascii=False).encode('utf-8')
        incoming = generation_ingress.record_generation_poll(actor,account.id,d.WeixinPollInput(request_id=uuid4(),
            expected_revision=current.checkpoint_revision,expected_cursor=current.upstream_cursor),wire,database=database)
        targets.append({'cid':str(target.scope.conversation_id),'descriptors':[str(item.id) for item in incoming.descriptors]})
    return str(root.scope.conversation_id), targets


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    repo=Path(__file__).resolve().parents[1];workspace=output/'synthetic-workspace'
    username,password='synthetic','Test-4271'
    initialize_workspace(workspace,username,password,data_parent=output)
    settings=load_settings()
    database=Database('sqlite:///'+str(workspace/'workbench.db'),workspace/'protected',settings,initialize_schema=False)
    backup._mark_storage_flags(database)
    with database.session() as db:
        token,_=login(username,password,db);actor=authenticate(token,db)
    cid,targets=seed(database,actor)
    with database.session() as db:
        originals=[tuple(row) for row in db.execute(text('SELECT * FROM weixin_inbox_descriptors ORDER BY rowid'))]
    app=create_app(settings,database=database,assistant_home_enabled=True,purpose='mock_demo')
    import uvicorn
    listener=socket.socket();listener.bind(('127.0.0.1',0));base='http://127.0.0.1:'+str(listener.getsockname()[1])
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
    thread=Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
    deadline=time.monotonic()+15
    while not server.started and time.monotonic()<deadline:time.sleep(.05)
    assert server.started
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(repo/'.local/scrapling/browsers'))
    from playwright.sync_api import sync_playwright, expect
    expect.set_options(timeout=20000)
    report={'steps':[],'visual':[],'external_requests':[],'page_errors':[],'writes':[],'status':'RUNNING'}
    try:
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':1280,'height':1000})
            def local_only(route):
                if route.request.url.startswith(base+'/'):route.continue_()
                else:report['external_requests'].append(route.request.url);route.abort()
            context.route('**/*',local_only)
            assert context.request.post(base+'/api/login',data={'username':username,'password':password}).status==200
            page=context.new_page();page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            page.on('request',lambda req:report['writes'].append(req.method+' '+req.url.removeprefix(base)) if req.method=='POST' and '/dispatches' in req.url else None)
            page.goto(base+'/assistant/'+cid)
            page.get_by_role('button',name='审查合同 · 模拟',exact=True).first.click()
            page.locator('#weixin-pending-panel > summary').click()
            choose=page.locator('#weixin-pending-target');expect(choose.locator('option')).to_have_count(4)
            choose.select_option(targets[0]['cid']);page.locator('#weixin-pending-read').click()
            rows=page.locator('#weixin-pending-list li');expect(rows).to_have_count(20)
            assert '正文不得出现' not in page.locator('#weixin-pending-list').inner_text()
            expect(rows.nth(1).locator('button')).to_be_disabled()
            page.locator('#weixin-pending-more').click();expect(rows).to_have_count(1)
            expect(rows.first.locator('button')).to_be_disabled()
            page.locator('#weixin-pending-read').click();expect(rows).to_have_count(20)
            report['steps'].append('historical target: 20 + 1 pagination, first-only delivery, no message body')
            rows.first.locator('button').focus();rows.first.locator('button').press('Enter')
            expect(page.locator('#weixin-pending-result')).to_contain_text('回执已确认')
            expect(rows).to_have_count(20)
            assert len(report['writes'])==1
            lost=[False]
            def lose_ack(route):
                if route.request.method=='POST':
                    response=route.fetch();assert response.status==200;lost[0]=True;route.abort('failed')
                else:route.continue_()
            path='**/api/assistant/conversations/'+cid+'/weixin-authorization/dispatches'
            page.route(path,lose_ack)
            rows.first.locator('button').click()
            expect(page.locator('#weixin-pending-notice')).to_contain_text('尚未确认')
            expect(choose).to_be_disabled();expect(page.locator('#task-collect')).to_be_disabled()
            old_url=page.url;page.locator('#new-conversation').click() if page.locator('#new-conversation').count() else None
            assert page.url==old_url
            queries=[]
            page.on('request',lambda req:queries.append(req.method) if '/dispatches/by-descriptor/' in req.url else None)
            page.locator('#weixin-pending-find').click()
            expect(page.locator('#weixin-pending-result')).to_contain_text('回执已确认');expect(rows).to_have_count(19)
            assert lost[0] and len(report['writes'])==2 and queries==['GET']
            page.unroute(path,lose_ack)
            report['steps'].append('lost POST ACK: exactly one POST, target/tasks/navigation locked, exact GET reconciles')
            choose.select_option(targets[1]['cid']);page.locator('#weixin-pending-read').click();expect(rows).to_have_count(1)
            for width in (1280,360):
                page.set_viewport_size({'width':width,'height':1000})
                page.locator('#weixin-pending-read').focus()
                page.locator('#weixin-pending-panel').screenshot(path=str(output/f'pending-{width}.png'))
                dims=page.evaluate('({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})')
                assert dims['scroll']<=dims['client'],dims
                report['visual'].append({'width':width,**dims,'screenshot':f'pending-{width}.png'})
            browser.close()
        with database.session() as db:
            assert [tuple(row) for row in db.execute(text('SELECT * FROM weixin_inbox_descriptors ORDER BY rowid'))]==originals
            report['counts']={table:db.scalar(text('SELECT count(*) FROM '+table)) for table in
                ('weixin_dispatch_receipts','task_inbox_events','task_executions','assistant_runs','assistant_model_attempts','review_runs')}
        assert report['counts']['weixin_dispatch_receipts']==report['counts']['task_inbox_events']==2
        assert all(report['counts'][table]==0 for table in ('task_executions','assistant_runs','assistant_model_attempts','review_runs'))
        assert not report['external_requests'] and not report['page_errors']
        report.update(status='PASS',original_descriptor_count=len(originals),original_descriptors_unchanged=True)
    except BaseException as error:
        report.update(status='FAIL',error=str(error));raise
    finally:
        server.should_exit=True;thread.join(timeout=10);database.engine.dispose()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
