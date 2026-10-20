"""Actual source app + synthetic library + Chromium. No provider configuration or real materials."""
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
import hashlib
import json
import socket
import sys
import time
import traceback

import uvicorn
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import text

from cn_contract.web.local_server import initialize_workspace, build_local_app
from cn_contract.library.law_sections import import_laws
from cn_contract.library.index import activate_generation, build_generation

PROJECT=Path.cwd()
CHROMIUM=PROJECT/'.local/scrapling/browsers/chromium-1243/chrome-win64/chrome.exe'
@contextmanager
def serve(app):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));sock.listen(32)
        server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
        thread=Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        try:
            deadline=time.monotonic()+30
            while not server.started:
                assert thread.is_alive() and time.monotonic()<deadline
                time.sleep(.03)
            yield 'http://127.0.0.1:'+str(sock.getsockname()[1])
        finally:
            server.should_exit=True;thread.join(30);assert not thread.is_alive()

target=Path(sys.argv[1]).resolve();target.mkdir(parents=True,exist_ok=False)
report={'exit_code':1,'checks':[],'page_errors':[],'external_requests':[], 'screens':[],
        'scope':'actual source HTTP app + independent synthetic SQLite law library + actual Chromium; no installed app',
        'physical_ime_tested':False,'physical_os_scaling_tested':False}
try:
    laws=target/'独立合成法条';laws.mkdir()
    (laws/'独立合成法规.md').write_text('# 纯合成资料\n第一条 合成租赁正文 <script>alert(1)</script>。\n第二条 合成租赁义务待核对。\n',encoding='utf-8')
    library=target/'合成法库';import_laws(library,laws,'synthetic');activate_generation(library,build_generation(library))
    root=target/'合成工作区';initialize_workspace(root,'合成检索律师','fixture123',data_parent=target)
    app=build_local_app(root,library_root=library,data_parent=target)
    assert app.state.assistant_generation_tasks.runtime is None
    with serve(app) as origin,sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(CHROMIUM),headless=True)
        page=browser.new_page(viewport={'width':1366,'height':900});page.set_default_timeout(15000)
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('dialog',lambda d:d.dismiss())
        page.on('request',lambda r:report['external_requests'].append(r.url) if not r.url.startswith(origin) else None)
        calls=[];page.on('request',lambda r:calls.append({'url':r.url,'method':r.method}))
        def shot(name):
            page.screenshot(path=str(target/(name+'.png')));report['screens'].append(name+'.png')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),name+' horizontal overflow'
        page.goto(origin+'/login');page.get_by_label('用户名').fill('合成检索律师');page.get_by_label('密码').fill('fixture123')
        page.get_by_role('button',name='登录',exact=True).click();page.wait_for_url(origin+'/assistant')
        page.locator('#more-skills summary').click();page.locator('[data-skill="legal_research"]').click()
        box=page.locator('#composer');expect(box).to_have_value('');assert not any('/researches' in c['url'] for c in calls)
        report['checks'].append('skill_selection_keeps_empty_input_and_does_not_query')
        box.fill('合成租赁');box.press('Shift+Enter');expect(box).to_have_value('合成租赁\n')
        box.fill('合成租赁');box.dispatch_event('compositionstart');box.dispatch_event('keydown',{'key':'Enter','isComposing':True,'keyCode':229})
        assert not any(c['method']=='POST' and '/researches' in c['url'] for c in calls)
        box.dispatch_event('compositionend');page.wait_for_timeout(300)
        expect(page.locator('#send')).to_be_enabled();box.press('Enter')
        expect(page.locator('.citation-link').first).to_be_visible()
        assert sum(c['method']=='POST' and c['url'].endswith('/researches') for c in calls)==1
        report['checks'].append('actual_Enter_single_local_query_and_synthetic_IME_ShiftEnter_guard')
        expect(box).to_have_value('');page.locator('.citation-link').first.focus();page.keyboard.press('Enter')
        expect(page.locator('#citation-preview')).to_be_visible();expect(page.locator('.citation-quote')).to_contain_text('合成租赁')
        expect(page.locator('#citation-preview-content')).to_contain_text('历史片段')
        assert page.locator('#citation-preview script').count()==0
        shot('desktop-saved-citation')
        page.keyboard.press('Escape');expect(page.locator('#citation-preview')).to_be_hidden()
        assert page.locator('.citation-link').first.evaluate('(e)=>e===document.activeElement')
        report['checks'].append('keyboard_source_open_escape_restore_and_literal_markup')
        page.set_viewport_size({'width':390,'height':844});page.locator('#body-size').select_option('20')
        page.locator('.citation-link').first.click();expect(page.locator('.citation-quote')).to_contain_text('合成租赁')
        shot('narrow-large-citation');page.locator('#close-citation-preview').click()
        page.set_viewport_size({'width':800,'height':600});page.locator('.citation-link').first.scroll_into_view_if_needed();shot('small-window-results')
        report['checks'].append('390_and_800_width_20px_text_without_horizontal_overflow')
        # Removing only the fixture's active marker makes current search unavailable; saved snapshots remain readable.
        marker=library/'current.json';old=marker.read_bytes();marker.unlink()
        page.reload();expect(page.locator('.citation-link').first).to_be_visible();page.locator('.citation-link').first.click()
        expect(page.locator('.citation-quote')).to_contain_text('合成租赁');page.locator('#close-citation-preview').click()
        report['checks'].append('offline_library_history_reopens_without_search_POST')
        page.locator('#more-skills summary').click();page.locator('[data-skill="legal_research"]').click()
        box.fill('合成租赁');expect(page.locator('#send')).to_be_enabled();box.press('Enter')
        expect(page.locator('.research-result').last).to_contain_text('暂不可用')
        marker.write_bytes(old)
        box.fill('独立零命中关键词');expect(page.locator('#send')).to_be_enabled();box.press('Enter')
        expect(page.locator('.research-result').last).to_contain_text('未命中')
        report['checks'].append('actual_not_ready_and_zero_hits_are_distinct')
        page.locator('.citation-link').first.click();page.locator('#new-conversation').click()
        expect(page.locator('#citation-preview')).to_be_hidden();expect(page.locator('#citation-preview-content')).to_be_empty()
        expect(page.locator('#history')).to_be_empty()
        report['checks'].append('new_conversation_clears_history_and_source_immediately')
        with app.state.database.session() as db:
            report['counts']={name:db.execute(text('SELECT count(*) FROM '+name)).scalar_one() for name in
                ('assistant_handler_receipts','assistant_library_citations','assistant_model_attempts','assistant_model_outputs','assistant_judge_attempts')}
        assert report['counts']['assistant_handler_receipts']==3
        assert all(report['counts'][name]==0 for name in ('assistant_model_attempts','assistant_model_outputs','assistant_judge_attempts'))
        assert not any('/generations' in c['url'] and c['method']=='POST' for c in calls)
        assert not report['page_errors'] and not report['external_requests']
        report['checks'].append('zero_model_Jev_rows_and_zero_external_requests')
        report['requests']=calls;browser.close()
    report['exit_code']=0
except BaseException:
    report['traceback']=traceback.format_exc();print(report['traceback'])
finally:
    (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'exit_code':report['exit_code'],'checks':report['checks']},ensure_ascii=False))
raise SystemExit(report['exit_code'])
