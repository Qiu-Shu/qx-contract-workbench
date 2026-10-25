"""Validate explicit history UI with synthetic local APIs and a real qxbak copy.

No account login, provider, worker, transport, real contract or Electron starts.
Raw databases, backup archives and screenshots stay in the required local output.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.config import load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login
from cn_contract.task_drafts import service as tasks
from cn_contract.web.app import create_app
from cn_contract.web.local_server import initialize_workspace
from cn_contract.web.recovery import attach_recovery
from cn_contract.weixin_inbox import accounts
from validate_weixin_authorization_browser import (
    USERNAME, PASSWORD, PASSPHRASE, counts as previous_counts, start_server,
)


PRODUCT_FILES = (
    'src/cn_contract/web/static/assistant-weixin-generations.mjs',
    'src/cn_contract/web/static/assistant-weixin.mjs',
    'src/cn_contract/web/static/assistant.mjs',
    'src/cn_contract/web/static/assistant.css',
    'src/cn_contract/web/templates/assistant.html',
)


def counts(database):
    result = previous_counts(database)
    with database.session() as db:
        for name in ('weixin_peer_generations', 'task_channel_bindings'):
            result[name] = db.scalar(text('SELECT count(*) FROM '+name))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[1]

    def hashes():
        return {name:hashlib.sha256((project/name).read_bytes()).hexdigest() for name in PRODUCT_FILES}

    frozen = hashes()
    settings = load_settings()
    source = initialize_workspace(output/'native-source', USERNAME, PASSWORD, data_parent=output)
    database = Database('sqlite:///'+str(source/'workbench.db'), source/'protected', settings, initialize_schema=False)
    backup._mark_storage_flags(database)
    with database.session() as db:
        token, _ = login(USERNAME, PASSWORD, db)
        actor = authenticate(token, db)
        views = [service.create_conversation(actor, d.AssistantConversationCreateInput(
            request_id=uuid4(), display_title=title), db) for title in (
                '独立合成历史入口', '独立合成目标甲', '独立合成目标乙', '独立合成目标丙')]
        root_binding = tasks.create_binding(actor, views[0].scope.conversation_id, db)
        tasks.create_binding(actor, views[2].scope.conversation_id, db)
    account = accounts.create_synthetic_account(actor, d.WeixinAccountCreateInput(
        bot_account_id='synthetic-history-ui-bot'), database=database)
    accounts.bind_synthetic_peer(actor, account.id, d.WeixinPeerBindInput(
        sender_peer_id='synthetic-history-ui-peer', task_binding_id=root_binding.id,
        expected_scope=views[0].scope), database=database)
    app = create_app(settings, database=database, assistant_home_enabled=True, purpose='mock_demo')
    base, server, thread, listener = start_server(app)
    servers, databases, allowed = [(server, thread, listener)], [database], {base}
    cid = str(views[0].scope.conversation_id)
    path = '/api/assistant/conversations/'+cid+'/weixin-authorization/generations'
    report = dict(scope='source FastAPI + local synthetic Chromium; installed Electron NOT_RUN',
        purpose=app.state.purpose, product_source_sha256=frozen, steps=[], requests=[],
        external_browser_requests=[], page_errors=[], screenshots=[], initial_counts=counts(database))
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(project/'.local/scrapling/browsers'))
    from playwright.sync_api import sync_playwright, expect
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width':1280, 'height':1000})

            def guard(route):
                if any(route.request.url.startswith(value+'/') for value in allowed):
                    route.continue_()
                else:
                    report['external_browser_requests'].append(route.request.url)
                    route.abort()

            def track(request):
                if '/weixin-authorization' in request.url or '/task-bindings' in request.url:
                    report['requests'].append(dict(method=request.method, path=urlsplit(request.url).path))

            context.route('**/*', guard)
            context.on('request', track)
            assert context.request.post(base+'/api/login', data={'username':USERNAME,'password':PASSWORD}).status == 200
            page = context.new_page()
            page.on('pageerror', lambda error:report['page_errors'].append(str(error)))

            def element(name):
                return page.locator('#weixin-generation-'+name)

            def open_panel(target_base):
                page.goto(target_base+'/assistant/'+cid)
                page.locator('#task-draft-panel > summary').click()
                element('panel').locator('summary').click()
                expect(element('state')).to_contain_text('当前目标历史')

            def preview(index):
                expect(element('target')).to_be_enabled()
                element('target').select_option(str(views[index].scope.conversation_id))
                element('reason').fill('独立合成明确追加目标历史 '+str(index))
                element('prepare').click()
                expect(element('preview')).to_contain_text(views[index].display_title)
                expect(element('save')).to_be_enabled()

            open_panel(base)
            assert counts(database) == report['initial_counts']
            preview(1)
            assert counts(database) == report['initial_counts'], 'preview must never create a missing binding'
            for width, label in ((1280, 'desktop'), (360, 'narrow')):
                page.set_viewport_size({'width':width,'height':1000})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), label+' overflow'
                element('save').focus()
                expect(element('save')).to_be_focused()
                filename = 'browser-'+label+'-preview.png'
                page.screenshot(path=str(output/filename), full_page=True)
                report['screenshots'].append(filename)
            report['viewports'] = dict(desktop=1280, narrow=360, horizontal_overflow=False, keyboard_focus=True)
            page.set_viewport_size({'width':1280,'height':1000})
            element('save').focus()
            element('save').press('Enter')
            expect(element('notice')).to_contain_text('已保存目标历史')
            expect(element('state')).to_contain_text('1 代')
            assert counts(database)['weixin_peer_generations'] == 1
            assert counts(database)['task_channel_bindings'] == 3
            report['steps'].append('read/preview zero writes; focused Enter creates missing binding then generation one exactly once')
            preview(2)
            lost = []

            def lose_generation_ack(route):
                if route.request.method != 'POST':
                    route.continue_()
                    return
                response = route.fetch()
                assert response.status == 200, response.text()
                lost.append(dict(request=route.request.post_data_json, receipt=response.json()))
                route.abort('failed')

            context.route(base+path, lose_generation_ack)
            element('save').click()
            expect(element('notice')).to_contain_text('不会自动重发')
            expect(element('find')).to_be_enabled()
            expect(element('clear')).to_be_disabled()
            assert len(lost) == 1 and counts(database)['weixin_peer_generations'] == 2
            element('find').click()
            expect(element('notice')).to_contain_text('已保存目标历史')
            expect(element('state')).to_contain_text('2 代')
            lookup = path+'/by-request/'+lost[0]['request']['request_id']
            assert dict(method='GET', path=lookup) in report['requests']
            context.unroute(base+path, lose_generation_ack)
            report['steps'].append('generation two commits with lost ACK; fixed request GET confirms receipt, no second POST')
            preview(3)
            binding_path = '/api/assistant/conversations/'+str(views[3].scope.conversation_id)+'/task-bindings'
            lost_binding = []

            def lose_binding_ack(route):
                response = route.fetch()
                assert response.status == 200, response.text()
                lost_binding.append(response.json())
                route.abort('failed')

            context.route(base+binding_path, lose_binding_ack)
            element('save').click()
            expect(element('notice')).to_contain_text('不会自动重发')
            assert len(lost_binding) == 1 and counts(database)['task_channel_bindings'] == 4
            assert counts(database)['weixin_peer_generations'] == 2
            element('find').click()
            expect(element('notice')).to_contain_text('再次明确保存')
            assert counts(database)['weixin_peer_generations'] == 2
            element('save').click()
            expect(element('state')).to_contain_text('3 代')
            expect(element('notice')).to_contain_text('收件仍暂停')
            assert counts(database)['weixin_peer_generations'] == 3
            report['steps'].append('binding commits with lost ACK; GET only confirms binding; a second explicit save appends generation three')
            report['source_counts'] = counts(database)
            archive = output/'synthetic-history.qxbak'
            workspace_backup.create_workspace_backup(source, archive, PASSPHRASE, data_parent=output)
            restored_info = workspace_backup.restore_workspace_backup(archive, output/'restored', PASSPHRASE)
            restored_root = Path(restored_info['restored_root'])
            restored = Database('sqlite:///'+str(restored_root/'workbench.db'), restored_root/'protected', settings, initialize_schema=False)
            backup._mark_storage_flags(restored)
            databases.append(restored)
            restored_app = create_app(settings, database=restored, assistant_home_enabled=True, purpose='mock_demo')
            attach_recovery(restored_app, restored)
            assert restored_app.state.recovery_copy is True
            restored_base, rs, rt, rl = start_server(restored_app)
            servers.append((rs, rt, rl))
            allowed.add(restored_base)
            login_response = context.request.post(restored_base+'/api/login', data={'username':USERNAME,'password':PASSWORD})
            assert login_response.status == 200
            open_panel(restored_base)
            expect(element('state')).to_contain_text('3 代')
            for name in ('target', 'reason', 'prepare', 'save'):
                expect(element(name)).to_be_disabled()
            found = context.request.get(restored_base+lookup)
            assert found.status == 200 and found.json() == lost[0]['receipt']
            denied = context.request.post(restored_base+path, headers={
                'X-CSRF-Token':login_response.json()['csrf_token'], 'Origin':restored_base}, data=lost[0]['request'])
            assert denied.status == 409 and denied.json()['code'] == 'BLOCKED_LIVE'
            report['restored_counts'] = counts(restored)
            assert report['restored_counts'] == report['source_counts']
            report['restored_lookup_status'], report['restored_post_status'] = found.status, denied.status
            report['steps'].append('actual qxbak restore preserves three histories; UI disables writes, fixed receipt GET200 and fenced POST409')
            browser.close()
        for values in (report['source_counts'], report['restored_counts']):
            assert values['weixin_accounts'] == values['weixin_peer_bindings'] == 1
            assert values['weixin_peer_generations'] == 3 and values['task_channel_bindings'] == 4
            assert all(values[name] == 0 for name in values if name not in (
                'weixin_accounts', 'weixin_peer_bindings', 'weixin_peer_generations', 'task_channel_bindings'))
        assert not report['external_browser_requests'] and not report['page_errors']
        methods = Counter(item['method'] for item in report['requests'])
        report['request_counts'] = dict(methods)
        assert methods['POST'] == 5, 'three generation + two binding POST only'
        assert hashes() == frozen, 'product source drift'
        report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report['status'] = 'PASS'
    except BaseException as error:
        report['status'], report['error'] = 'FAIL', str(error)
        raise
    finally:
        for server, thread, listener in reversed(servers):
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
        for item in databases:
            item.engine.dispose()
        (output/'browser-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
