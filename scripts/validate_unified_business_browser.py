"""Disposable fictional unified-chat acceptance; no external requests allowed."""
import argparse
import json
import os
from pathlib import Path
import socket
from threading import Thread
import time
from uuid import uuid4

from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.review.synthetic import select_fixture
from cn_contract.security import authenticate, login, provision_user
from cn_contract.storage_bootstrap import initialize_storage
from cn_contract.web.app import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    database = Database('sqlite:///'+str(output/'synthetic.sqlite'), output/'store', settings)
    initialize_storage(database)
    with database.session() as db:
        db.execute(text('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)'))
        db.execute(text('INSERT INTO local_workspace_identity VALUES (:id)'), {'id':str(uuid4())})
        provision_user('synthetic-lawyer', 'only-fictional-browser-pass', {d.Role.HANDLING_LAWYER}, db)
        token, _ = login('synthetic-lawyer', 'only-fictional-browser-pass', db)
        actor = authenticate(token, db)
        view = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
    _, _, source_path, _ = select_fixture('sales')
    app = create_app(settings, database=database, assistant_home_enabled=True)
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
    assert server.started
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(Path(__file__).resolve().parents[1]/'.local/scrapling/browsers'))
    from playwright.sync_api import sync_playwright, expect
    report = {'scope':'source FastAPI + Chromium; synthetic only; not installed desktop or real model',
              'steps':[], 'page_errors':[], 'external_requests':[]}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width':1280, 'height':900})
            def route(request):
                if request.request.url.startswith(base+'/'):
                    request.continue_()
                else:
                    report['external_requests'].append(request.request.url)
                    request.abort()
            context.route('**/*', route)
            response = context.request.post(base+'/api/login', data={'username':'synthetic-lawyer','password':'only-fictional-browser-pass'})
            assert response.status == 200
            page = context.new_page()
            page.on('pageerror', lambda error:report['page_errors'].append(str(error)))
            conversation_url = base+'/assistant/'+str(view.scope.conversation_id)
            page.goto(conversation_url)
            def send(value):
                page.locator('#composer').fill(value)
                expect(page.locator('#send')).to_be_enabled()
                page.locator('#send').click()
                expect(page.locator('#composer')).to_have_value('')
            send('帮我审查这个合同')
            expect(page.locator('#task-current')).to_contain_text('帮我审查这个合同')
            task_id = page.locator('#task-select').input_value()
            assert task_id
            report['steps'].append('natural contract intent creates task from shared composer')
            page.locator('#add-material').click()
            page.locator('#material-file').set_input_files(str(source_path))
            page.locator('#material-consent').check()
            page.locator('#upload-material').click()
            expect(page.locator('#material-list')).to_contain_text(source_path.name)
            expect(page.locator('#upload-material')).to_be_disabled()
            send('补充主合同，请继续审查')
            expect(page.get_by_role('button', name='冻结材料', exact=True)).to_be_enabled()
            assert page.locator('#task-select').input_value() == task_id
            report['steps'].append('upload auto-parses locally; supplemental input retains same task')
            page.get_by_role('button', name='冻结材料', exact=True).click()
            page.get_by_label('档案名称', exact=True).fill('统一聊天合成审查')
            page.get_by_label('合同类型', exact=True).select_option('sales')
            page.get_by_label('我方角色', exact=True).select_option('buyer')
            page.get_by_label('合同状态', exact=True).select_option('pre_sign')
            page.get_by_role('button', name='保存档案并读取事实', exact=True).click()
            page.get_by_text('核对事实 · 当前第 1 版', exact=True).click()
            for select in page.locator('#task-current fieldset select').all():
                select.select_option('confirmed')
            for reason in page.locator('#task-current fieldset input').all():
                reason.fill('验收人员核对独立虚构样本')
            page.get_by_role('button', name='保存本次事实核对', exact=True).click()
            expect(page.get_by_text('核对事实 · 当前第 2 版', exact=True)).to_be_visible()
            page.get_by_role('button', name='运行模拟审查', exact=True).click()
            expect(page.locator('#task-current')).to_contain_text('本次模拟审查结果', timeout=30000)
            assert page.url == conversation_url
            report['steps'].append('case creation, explicit fact decisions and Mock review stay in same chat')
            page.screenshot(path=str(output/'chat-contract-desktop.png'), full_page=True)
            page.reload()
            expect(page.locator('#task-current')).to_contain_text('本次模拟审查结果')
            send('整理这个案件')
            expect(page.locator('#history')).to_contain_text('初步事实时间线')
            send('站在对方律师和法官角度模拟')
            expect(page.locator('#history')).to_contain_text('庭审通用准备提纲')
            report['steps'].append('case and court local preparation reuse selected material after reload')
            page.set_viewport_size({'width':390,'height':844})
            report['narrow_no_overflow'] = page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(output/'chat-narrow.png'), full_page=True)
            assert report['narrow_no_overflow']
            assert not report['page_errors'] and not report['external_requests']
            browser.close()
        with database.session() as db:
            report['counts'] = {name:db.scalar(text('SELECT count(*) FROM '+name)) for name in
                ('task_drafts','task_executions','review_runs','assistant_model_attempts','assistant_attachments')}
        assert report['counts'] == {'task_drafts':1,'task_executions':1,'review_runs':1,'assistant_model_attempts':0,'assistant_attachments':1}
        report['status'] = 'PASS'
    except BaseException as error:
        report['status']='FAIL'
        report['error']=str(error)
        raise
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        listener.close()
        database.engine.dispose()
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
