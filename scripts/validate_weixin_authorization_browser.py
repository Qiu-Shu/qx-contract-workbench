"""Exercise explicit synthetic peer authorization in disposable local Chromium.

Uses registered fictional DOCX bytes and real native backup/recovery APIs. No
worker, provider, real Weixin account, transport or installed Electron is started.
"""
import argparse
from collections import Counter
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import socket
from threading import Thread
import time
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.config import load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.review.synthetic import select_fixture
from cn_contract.security import authenticate, login
from cn_contract.task_drafts import service as tasks
from cn_contract.web.app import create_app
from cn_contract.web.local_server import initialize_workspace
from cn_contract.web.recovery import attach_recovery
from cn_contract.weixin_inbox import accounts


USERNAME, PASSWORD = 'synthetic-lawyer', 'fiction123'
PASSPHRASE = 'independent-fiction-browser-backup'
PRODUCT_FILES = (
    'src/cn_contract/domain.py', 'src/cn_contract/weixin_inbox/accounts.py',
    'src/cn_contract/weixin_inbox/conversation.py', 'src/cn_contract/web/weixin_authorization.py',
    'src/cn_contract/web/app.py', 'src/cn_contract/web/recovery.py',
    'src/cn_contract/web/static/assistant-weixin.mjs', 'src/cn_contract/web/static/assistant.mjs',
    'src/cn_contract/web/static/assistant.css', 'src/cn_contract/web/templates/assistant.html',
)


def hashes(root):
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in PRODUCT_FILES}


def counts(database):
    tables = ('weixin_accounts','weixin_peer_bindings','weixin_peer_scope_grants',
        'weixin_poll_receipts','weixin_inbox_descriptors','weixin_dispatch_receipts',
        'task_inbox_events','task_drafts','task_executions','assistant_attachments',
        'assistant_model_attempts','assistant_runs','review_runs')
    with database.session() as db:
        return {name:db.scalar(text('SELECT count(*) FROM '+name)) for name in tables}


def start_server(app):
    import uvicorn
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    base = 'http://127.0.0.1:'+str(listener.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = Thread(target=server.run, kwargs={'sockets':[listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic()+15
    while not server.started and time.monotonic()<deadline:
        time.sleep(.05)
    assert server.started, 'synthetic loopback server did not start'
    return base,server,thread,listener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--restore-diagnostics', action='store_true',
                        help='observe synthetic restore stages and own-process handles')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[1]
    before_hashes = hashes(project)
    settings = load_settings()
    root = initialize_workspace(output/'native-source',USERNAME,PASSWORD,data_parent=output)
    database = Database('sqlite:///'+str(root/'workbench.db'),root/'protected',settings,initialize_schema=False)
    backup._mark_storage_flags(database)
    with database.session() as db:
        token,_ = login(USERNAME,PASSWORD,db)
        actor = authenticate(token,db)
        bound = service.create_conversation(actor,d.AssistantConversationCreateInput(
            request_id=uuid4(),display_title='独立虚构收件授权验收'),db)
        unbound = service.create_conversation(actor,d.AssistantConversationCreateInput(
            request_id=uuid4(),display_title='独立虚构未绑定对话'),db)
        binding = tasks.create_binding(actor,bound.scope.conversation_id,db)
    account = accounts.create_synthetic_account(actor,d.WeixinAccountCreateInput(
        bot_account_id='synthetic-browser-bot'),database=database)
    mapping = accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(
        sender_peer_id='synthetic-browser-peer',task_binding_id=binding.id,
        expected_scope=bound.scope),database=database)
    app = create_app(settings,database=database,assistant_home_enabled=True,purpose='mock_demo')
    base,server,thread,listener = start_server(app)
    servers = [(server,thread,listener)]
    databases = [database]
    allowed_bases = {base}
    report = {'scope':'synthetic local Chromium + source FastAPI; installed Electron NOT_RUN',
        'purpose':app.state.purpose,'product_source_sha256':before_hashes,
        'steps':[],'external_browser_requests':[],'page_errors':[],
        'authorization_requests':[],'screenshots':[]}
    cid = str(bound.scope.conversation_id)
    path = '/api/assistant/conversations/'+cid+'/weixin-authorization'
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(project/'.local/scrapling/browsers'))
    from playwright.sync_api import sync_playwright, expect
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width':1280,'height':1000})

            def guard(route):
                if any(route.request.url.startswith(value+'/') for value in allowed_bases):
                    route.continue_()
                else:
                    report['external_browser_requests'].append(route.request.url)
                    route.abort()

            def track(request):
                if '/weixin-authorization' in request.url:
                    report['authorization_requests'].append(dict(method=request.method,path=urlsplit(request.url).path))

            context.route('**/*',guard)
            context.on('request',track)
            response = context.request.post(base+'/api/login',data={'username':USERNAME,'password':PASSWORD})
            assert response.status == 200,response.text()
            page = context.new_page()
            page.on('pageerror',lambda error:report['page_errors'].append(str(error)))

            def open_card(target_base,target_cid):
                page.goto(target_base+'/assistant/'+str(target_cid))
                page.locator('#task-draft-panel > summary').click()
                expect(page.locator('#weixin-authorization')).to_be_visible()

            def posts():
                return sum(item['method']=='POST' for item in report['authorization_requests'])

            open_card(base,unbound.scope.conversation_id)
            expect(page.locator('#weixin-state')).to_contain_text('本对话尚未绑定')
            assert counts(database)['weixin_peer_scope_grants'] == 0 and posts() == 0
            report['steps'].append('unbound page reads actual absence without creating a mapping or grant')
            open_card(base,cid)
            expect(page.locator('#weixin-state')).to_contain_text('与当前输入和材料版本一致')
            page.reload()
            page.get_by_role('button',name='审查合同 · 模拟',exact=True).first.click()
            expect(page.locator('#weixin-state')).to_contain_text('与当前输入和材料版本一致')
            assert counts(database)['weixin_peer_scope_grants'] == 0 and posts() == 0
            report['steps'].append('bound GET and reload remain current with zero grants and zero authorization POST')

            def upload(kind):
                _,_,source,_ = select_fixture(kind)
                page.locator('#add-material').click()
                page.locator('#material-file').set_input_files(str(source))
                page.locator('#material-consent').check()
                page.locator('#upload-material').click()
                expect(page.locator('#material-list')).to_contain_text(source.name)
                expect(page.locator('#weixin-state')).to_contain_text('需显式更新')
                expect(page.locator('#weixin-authorize')).to_be_enabled()
                return source.name

            first_name = upload('sales')
            assert counts(database)['weixin_peer_scope_grants'] == 0 and posts() == 0
            for width,label in ((1280,'desktop'),(360,'narrow')):
                page.set_viewport_size({'width':width,'height':1000})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),label+' horizontal overflow'
                page.locator('#weixin-authorize').focus()
                expect(page.locator('#weixin-authorize')).to_be_focused()
                screenshot = output/('browser-'+label+'-stale.png')
                page.screenshot(path=str(screenshot),full_page=True)
                report['screenshots'].append(screenshot.name)
            report['viewports'] = {'desktop':1280,'narrow':360,'horizontal_overflow':False,'keyboard_focus':True}
            page.set_viewport_size({'width':1280,'height':1000})
            page.locator('#weixin-authorize').focus()
            page.locator('#weixin-authorize').press('Enter')
            expect(page.locator('#weixin-notice')).to_contain_text('已保存本次授权')
            expect(page.locator('#weixin-state')).to_contain_text('与当前输入和材料版本一致')
            assert counts(database)['weixin_peer_scope_grants'] == 1 and posts() == 1
            report['steps'].append(first_name+' browser upload makes scope stale; focused Enter explicitly creates exactly one grant')
            page.reload()
            page.get_by_role('button',name='审查合同 · 模拟',exact=True).first.click()
            expect(page.locator('#weixin-state')).to_contain_text('与当前输入和材料版本一致')
            assert counts(database)['weixin_peer_scope_grants'] == 1 and posts() == 1
            report['steps'].append('reload reads current grant without another POST')
            second_name = upload('service')
            lost = []

            def lose_ack(route):
                if route.request.method != 'POST':
                    route.continue_()
                    return
                response = route.fetch()
                assert response.status == 200,response.text()
                lost.append({'request':route.request.post_data_json,'receipt':response.json()})
                assert counts(database)['weixin_peer_scope_grants'] == 2
                route.abort('failed')

            context.route(base+path+'/refresh',lose_ack)
            page.locator('#weixin-authorize').click()
            expect(page.locator('#weixin-notice')).to_contain_text('不会自动重发')
            expect(page.locator('#weixin-find')).to_be_enabled()
            assert len(lost) == 1 and counts(database)['weixin_peer_scope_grants'] == 2 and posts() == 2
            page.locator('#weixin-find').click()
            expect(page.locator('#weixin-notice')).to_contain_text('已找到本次授权回执')
            expect(page.locator('#weixin-state')).to_contain_text('与当前输入和材料版本一致')
            assert counts(database)['weixin_peer_scope_grants'] == 2 and posts() == 2
            lookup_path = path+'/refreshes/by-request/'+lost[0]['request']['request_id']
            assert any(item == {'method':'GET','path':lookup_path} for item in report['authorization_requests'])
            report['steps'].append(second_name+' upload then actual committed POST with aborted ACK; explicit GET finds the fixed receipt without resending')
            report['lost_ack_grant_revision'] = lost[0]['receipt']['revision']
            report['source_counts_before_restore'] = counts(database)

            archive = output/'browser-synthetic.qxbak'
            workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=output)
            observer = nullcontext()
            if args.restore_diagnostics:
                if __package__:
                    from .restore_publish_diagnostics import observe_restore
                else:
                    from restore_publish_diagnostics import observe_restore
                report['restore_diagnostics'] = []
                observer = observe_restore(output/'browser-restored', report['restore_diagnostics'])
            with observer:
                restored_info = workspace_backup.restore_workspace_backup(archive,output/'browser-restored',PASSPHRASE)
            restored_root = Path(restored_info['restored_root'])
            restored = Database('sqlite:///'+str(restored_root/'workbench.db'),restored_root/'protected',settings,initialize_schema=False)
            backup._mark_storage_flags(restored)
            databases.append(restored)
            restored_app = create_app(settings,database=restored,assistant_home_enabled=True,purpose='mock_demo')
            attach_recovery(restored_app,restored)
            assert restored_app.state.recovery_copy is True
            restored_base,rs,rt,rl = start_server(restored_app)
            servers.append((rs,rt,rl))
            allowed_bases.add(restored_base)
            logged = context.request.post(restored_base+'/api/login',data={'username':USERNAME,'password':PASSWORD})
            assert logged.status == 200,logged.text()
            restored_csrf = logged.json()['csrf_token']
            open_card(restored_base,cid)
            expect(page.locator('#weixin-state')).to_contain_text('恢复副本只读')
            expect(page.locator('#weixin-authorize')).to_be_hidden()
            page.locator('#weixin-read').click()
            expect(page.locator('#weixin-state')).to_contain_text('恢复副本只读')
            lookup = context.request.get(restored_base+lookup_path)
            assert lookup.status == 200 and lookup.json() == lost[0]['receipt']
            denied = context.request.post(restored_base+path+'/refresh',headers={'X-CSRF-Token':restored_csrf,'Origin':restored_base},data=lost[0]['request'])
            assert denied.status == 409 and denied.json()['code'] == 'BLOCKED_LIVE'
            with restored.session() as db:
                fences = [json.loads(value) for value in db.scalars(text('SELECT payload FROM ops_restore_fences'))]
            assert len(fences) == 1 and fences[0]['weixin_reauthorization_enabled'] is False
            assert counts(restored)['weixin_peer_scope_grants'] == 2
            screenshot = output/'browser-restored.png'
            page.screenshot(path=str(screenshot),full_page=True)
            report['screenshots'].append(screenshot.name)
            report['restored_counts'] = counts(restored)
            report['restored_lookup_status'],report['restored_post_status'] = lookup.status,denied.status
            report['steps'].append('actual authenticated qxbak restore + attach_recovery middleware renders read-only; GET receipt survives and POST is BLOCKED_LIVE')

            accounts.revoke_synthetic_peer(actor,mapping.id,d.WeixinRevokeInput(reason='独立合成浏览器撤权验收'),database=database)
            # Cookies are host-scoped, so log in again after visiting the second port.
            assert context.request.post(base+'/api/login',data={'username':USERNAME,'password':PASSWORD}).status == 200
            open_card(base,cid)
            expect(page.locator('#weixin-state')).to_contain_text('收件授权已撤销')
            expect(page.locator('#weixin-authorize')).to_be_hidden()
            report['steps'].append('public peer revocation is rendered as irreversible revoked state')
            report['source_counts_final'] = counts(database)
            browser.close()
        for values in (report['source_counts_final'],report['restored_counts']):
            assert values['weixin_peer_scope_grants'] == 2
            assert values['assistant_attachments'] == 2
            assert all(values[name] == 0 for name in ('weixin_poll_receipts','weixin_inbox_descriptors',
                'weixin_dispatch_receipts','task_inbox_events','task_drafts','task_executions',
                'assistant_model_attempts','assistant_runs','review_runs'))
        assert not report['external_browser_requests'] and not report['page_errors']
        assert hashes(project) == before_hashes,'product source changed during browser validation'
        report['authorization_request_counts'] = dict(Counter(item['method'] for item in report['authorization_requests']))
        assert report['authorization_request_counts']['POST'] == 2
        report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report['status'] = 'PASS'
    except BaseException as error:
        report['status'],report['error'] = 'FAIL',str(error)
        raise
    finally:
        for server,thread,listener in reversed(servers):
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
        for item in databases:
            item.engine.dispose()
        (output/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
