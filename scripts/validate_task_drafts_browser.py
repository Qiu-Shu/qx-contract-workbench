"""Run the task card against a disposable synthetic server and local Chromium.

Requires the project's existing optional Playwright development runtime. Never
opens an existing user workspace, launches a worker, or configures a provider.
"""
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
from cn_contract.matters import create_matter
from cn_contract.persistence import Database
from cn_contract.review.synthetic import select_fixture
from cn_contract.security import authenticate, login, provision_user
from cn_contract.storage_bootstrap import initialize_storage
from cn_contract.web.app import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--assisted', action='store_true', help='use the desktop assisted-draft policy')
    parser.add_argument('--format', choices=('docx', 'pdf'), default='docx',
        help='synthetic source format: registered DOCX fixture (default) or the fixed task-pdf-v1 native PDF')
    parser.add_argument('--order', choices=('instruction-first', 'material-first'), default='instruction-first',
        help='collection order: save the instruction before the material (default) or the material before the instruction')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    database = Database('sqlite:///' + str(output/'synthetic.sqlite'), output/'store', settings)
    initialize_storage(database)
    with database.session() as db:
        db.execute(text('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)'))
        db.execute(text('INSERT INTO local_workspace_identity VALUES (:id)'), {'id':str(uuid4())})
        provision_user('synthetic-lawyer', 'only-fictional-browser-pass', {d.Role.HANDLING_LAWYER}, db)
        token, _ = login('synthetic-lawyer', 'only-fictional-browser-pass', db)
        actor = authenticate(token, db)
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(
            request_id=uuid4(), display_title='任务收集浏览器合成验收'), db)
        matter = create_matter(d.MatterCreateInput(title='浏览器独立虚构案件', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('核对独立合成合同',)), actor, db)
    cid = conversation.scope.conversation_id
    if args.format == 'pdf':
        source_path = Path(__file__).resolve().parents[1]/'tests/fixtures/task-pdf-v1/native-sales.pdf'
    elif args.assisted:
        source_path = Path(__file__).resolve().parents[1]/'tests/fixtures/assisted-v1/sales-01.docx'
    else:
        _, _, source_path, _ = select_fixture('sales')
    format_label = args.format.upper()
    from cn_contract.acceptance.assisted_registry import load_seed_policy
    app = create_app(settings, database=database, assistant_home_enabled=True,
        purpose='assisted_draft' if args.assisted else 'mock_demo',
        assisted_policy=load_seed_policy() if args.assisted else None,
        local_materials_enabled=args.assisted)
    import uvicorn
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = Thread(target=server.run, kwargs={'sockets':[listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic()+15
    while not server.started and time.monotonic()<deadline:
        time.sleep(.05)
    assert server.started, 'synthetic server did not start'
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(Path(__file__).resolve().parents[1]/'.local/scrapling/browsers'))
    from playwright.sync_api import sync_playwright, expect
    report = {'scope':'synthetic Chromium + source FastAPI; not installed Electron acceptance',
              'purpose':app.state.purpose, 'order':args.order, 'format':args.format,
              'steps':[], 'external_browser_requests':[], 'page_errors':[]}
    base = f'http://127.0.0.1:{port}'
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width':1280,'height':1000})
            def route(request):
                if request.request.url.startswith(base+'/'):
                    request.continue_()
                else:
                    report['external_browser_requests'].append(request.request.url)
                    request.abort()
            context.route('**/*', route)
            response = context.request.post(base+'/api/login', data={
                'username':'synthetic-lawyer', 'password':'only-fictional-browser-pass'})
            assert response.status == 200, response.text()
            page = context.new_page()
            page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
            page.goto(base+'/assistant/'+str(cid))
            page.get_by_role('button', name='审查合同 · 模拟', exact=True).first.click()
            expect(page.locator('#task-instruction')).to_be_enabled()
            def upload_and_parse():
                page.locator('#add-material').click()
                page.locator('#material-file').set_input_files(str(source_path))
                page.locator('#material-consent').check()
                if args.assisted:
                    page.locator('#material-purpose').select_option('synthetic')
                page.locator('#upload-material').click()
                expect(page.locator('#material-list')).to_contain_text(source_path.name)
                page.get_by_role('button', name='核对原文', exact=True).click()
                page.get_by_role('button', name='读取 ' + format_label, exact=True).click()
                expect(page.locator('#material-preview')).to_contain_text('已读取，内容仍待核实')
                page.locator('#close-material-preview').click()
            if args.order == 'instruction-first':
                page.locator('#task-instruction').fill('帮我审查合同，重点核对付款与交付。')
                page.locator('#task-collect').click()
                expect(page.locator('#task-current')).to_contain_text('帮我审查合同')
                task_id = page.locator('#task-select').input_value()
                assert task_id
                report['steps'].append('instruction persisted before material collection')
                upload_and_parse()
                report['steps'].append(f'registered synthetic {format_label} uploaded and parsed through browser controls')
                page.locator('#task-attachments input[type=checkbox]').check()
                page.locator('#task-collect').click()
            else:
                upload_and_parse()
                report['steps'].append(f'registered synthetic {format_label} uploaded and parsed through browser controls')
                page.locator('#task-attachments input[type=checkbox]').check()
                page.locator('#task-collect').click()
                expect(page.locator('#task-current')).to_contain_text('补充审查指令')
                expect(page.get_by_role('button', name='冻结材料', exact=True)).to_be_disabled()
                task_id = page.locator('#task-select').input_value()
                assert task_id
                with database.session() as db:
                    assert db.scalar(text('SELECT count(*) FROM task_executions')) == 0
                report['steps'].append('attachment saved to task draft without instruction; freeze blocked and no execution created')
                page.locator('#task-instruction').fill('帮我审查合同，重点核对付款与交付。')
                page.locator('#task-collect').click()
                expect(page.locator('#task-current')).to_contain_text('帮我审查合同')
                report['steps'].append('review instruction appended to the same task draft')
            expect(page.get_by_role('button', name='冻结材料', exact=True)).to_be_enabled()
            page.get_by_role('button', name='冻结材料', exact=True).click()
            expect(page.locator('#task-current')).to_contain_text('待选择案件')
            expect(page.locator('#task-current select')).to_be_enabled()
            page.locator('#task-current select').select_option(str(matter.id))
            page.get_by_role('button', name='准备材料并确认事实', exact=True).click()
            page.wait_for_url('**/facts')
            expect(page.locator('#facts [data-fact]').first).to_be_visible()
            report['steps'].append(f'frozen {format_label} copied to case and unconfirmed facts rendered')
            for decision in page.locator('#facts select[name=decision]').all():
                decision.select_option('confirmed')
            with page.expect_response(lambda r:'/facts/confirm' in r.url and r.request.method=='POST') as confirmation:
                page.get_by_role('button', name='保存事实确认', exact=True).click()
            assert confirmation.value.status == 200
            page.goto(base+'/assistant/'+str(cid)+'#task-'+task_id)
            page.get_by_role('button', name='审查合同 · 模拟', exact=True).first.click()
            expect(page.get_by_role('button', name='运行模拟审查', exact=True)).to_be_enabled()
            page.get_by_role('button', name='运行模拟审查', exact=True).click()
            expect(page.locator('#task-current')).to_contain_text('模拟审查已完成', timeout=30000)
            page.screenshot(path=str(output/'task-completed.png'), full_page=True)
            report['steps'].append('human fixture confirmations then exactly one Mock result')
            page.reload()
            page.get_by_role('button', name='审查合同 · 模拟', exact=True).first.click()
            # Conversation navigation can remove the fragment; select the saved task explicitly.
            page.locator('#task-select').select_option(task_id)
            expect(page.locator('#task-current')).to_contain_text('模拟审查已完成')
            page.set_viewport_size({'width':840,'height':900})
            report['small_viewport_no_horizontal_overflow'] = page.evaluate(
                'document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(output/'task-small.png'), full_page=True)
            report['steps'].append('refresh recovered saved execution without another review')
            page.get_by_role('link', name='查看模拟审查结果', exact=True).click()
            page.wait_for_url('**/review')
            assert page.locator('body').inner_text().find('18') >= 0
            report['steps'].append('saved internal review page reachable')
            browser.close()
        with database.session() as db:
            report['counts'] = {table:db.scalar(text('SELECT count(*) FROM '+table)) for table in
                ('task_inbox_events','task_drafts','task_executions','document_versions','review_runs','assistant_runs')}
        counts = report['counts']
        assert counts['task_inbox_events'] == 2 and counts['task_drafts'] == 1 and counts['task_executions'] == 1
        assert counts['review_runs'] == 1 and counts['assistant_runs'] == 0
        assert not report['external_browser_requests'] and not report['page_errors']
        report['status'] = 'PASS'
    except BaseException as error:
        report['status'] = 'FAIL'
        report['error'] = str(error)
        raise
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        database.engine.dispose()
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
