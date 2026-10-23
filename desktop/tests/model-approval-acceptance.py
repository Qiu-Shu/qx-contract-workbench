"""Actual native confirmation, source loopback or frozen grant-without-send.

Uses the existing actual-main observer. All accounts/text/credentials are synthetic.
No test provider is packaged and the frozen path never submits an approved POST.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Queue
import re
import sqlite3
import subprocess
import sys
from threading import Thread
import time
from uuid import uuid4

from playwright.sync_api import Error as BrowserError, expect, sync_playwright

PROJECT = Path(__file__).resolve().parents[2]
SECRET = 'synthetic-native-secret-approval-20261019'
JUDGE_SECRET = 'synthetic-native-secret-judge-approval-20261020'
CONTENT = '独立合成咨询：虚构客户希望核对交货日期，尚未核实事实。'
JUDGE_CONTENT = '另一份独立合成咨询：虚构客户询问返还样品的步骤，陈述与依据仍待律师核验。'
LONG = '<script>禁止执行合成标记</script>\n' + '独立合成材料；客户陈述尚未核实，需要律师核对时间及原件。\n' * 110


def hashes():
    result = subprocess.run(['git', 'ls-files', '-z', '-co', '--exclude-standard', '--', 'src', 'desktop',
        'tests', 'scripts', 'config', 'schemas', 'pyproject.toml', 'requirements.lock'], cwd=PROJECT,
        capture_output=True, check=True)
    return {p: hashlib.sha256((PROJECT/p).read_bytes()).hexdigest() for p in
        sorted(set(result.stdout.decode('utf-8').split('\0'))-{''}) if (PROJECT/p).is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=Path)
    parser.add_argument('legacy_frozen', nargs='?', type=Path)
    parser.add_argument('--frozen', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--judge', action='store_true')
    modes.add_argument('--judge-closed', action='store_true')
    modes.add_argument('--profile', action='store_true')
    modes.add_argument('--profile-ui', action='store_true')
    options = parser.parse_args()
    if options.frozen and options.legacy_frozen: parser.error('choose one frozen argument')
    target = options.target.resolve(); target.mkdir(parents=True, exist_ok=False)
    frozen = options.frozen or options.legacy_frozen
    if frozen: frozen = frozen.resolve(); assert frozen.is_file()
    if (options.profile or options.profile_ui) and frozen: parser.error('profile acceptance is source-only')
    judge_mode = options.judge or options.judge_closed
    data = target/'中文 合成确认资料'; launch = target/'launch'; launch.mkdir()
    report = {'status': 'running', 'checks': [], 'source_before': hashes(), 'real_model_execution': 'not_requested',
        'backend': 'frozen_grant_without_send' if frozen else 'source_loopback', 'exit_code': 1,
        'page_errors': [], 'requests': [], 'profile_mode': options.profile, 'profile_ui': options.profile_ui, 'judge_mode': 'synthetic_budget' if options.judge else
            'production_default_closed' if options.judge_closed else 'legacy_main',
        'frozen_network_observation': 'not_instrumented' if frozen else None}
    if frozen: report['exe_sha256'] = hashlib.sha256(frozen.read_bytes()).hexdigest()
    posts = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            try:
                if self.path == '/v1/systemone':
                    assert options.judge and not frozen
                    assert self.headers['Authorization'] == 'Bearer '+JUDGE_SECRET
                    body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    assert body['model'] == 'jev-1.13.0'
                    assert body['state'] == {'latest_request': JUDGE_CONTENT, 'selected_skill': None}
                    assert list(body['questions']) == ['primary_intent']
                    posts.append({'provider': 'judge', 'content_sha256': hashlib.sha256(JUDGE_CONTENT.encode()).hexdigest()})
                    probabilities = dict.fromkeys(('client_reply', 'material_organize', 'contract_review',
                        'content_draft', 'legal_research', 'unknown'), 0)
                    probabilities['client_reply'] = 1
                    response = {'model': 'jev-1.13.0', 'answers': {'primary_intent': {'type': 'choice',
                        'choice': 'client_reply', 'probabilities': probabilities, 'confidence': 1}},
                        'usage': {'input_tokens': 25, 'output_tokens': 2}}
                    self.send_response(200); self.send_header('Content-Type', 'application/json')
                    self.send_header('x-typesafe-request-id', 'synthetic-ui-judge'); self.end_headers()
                    self.wfile.write(json.dumps(response).encode()); return
                assert self.path == '/chat/completions'
                assert self.headers['Authorization'] == 'Bearer '+SECRET
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                source = json.loads(body['messages'][1]['content'])
                assert source['content'] in ((CONTENT, JUDGE_CONTENT) if options.judge else (CONTENT,))
                posts.append({'provider': 'main', 'content_sha256': hashlib.sha256(source['content'].encode()).hexdigest()})
                if options.profile_ui:
                    assert set(source) == {'content'}, 'ARCHIVE_HISTORY_MUST_STAY_LOCAL'
                    candidate = {'text': '独立合成候选：交货事项仍需律师核对。', 'citations': [],
                        'profile_changes': [{'field':'consultation','value':{'kind':'text','value':CONTENT},
                            'origin':'user_statement','quotes':[{'start':0,'end':len(CONTENT),'quote':CONTENT}]}]}
                else:
                    candidate = {'text': '独立合成候选：交货事项仍需律师核对。', 'citations': [
                        {'message_id': source['message_id'], 'quote_sha256': source['quote_sha256']}]}
                response = {'id': 'synthetic-native-confirmation', 'model': 'deepseek-flash',
                    'object': 'chat.completion', 'created': 1, 'choices': [{'index': 0, 'finish_reason': 'stop',
                    'message': {'role': 'assistant', 'content': json.dumps(candidate, ensure_ascii=False)}}],
                    'usage': {'prompt_tokens': 30, 'completion_tokens': 12, 'total_tokens': 42}}
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps(response).encode())
            except Exception:
                report['provider_error'] = True; self.send_response(500); self.end_headers(); self.wfile.write(b'{}')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    Thread(target=server.serve_forever, daemon=True).start()
    proc = None; page = None; logs = {'stdout': [], 'stderr': []}
    def passed(name): report['checks'].append(name); print('PASS '+name, flush=True)
    try:
        env = {**os.environ, 'QX_PROBE_EVIDENCE': str(launch), 'QX_DESKTOP_DATA_PARENT': str(data),
            'PYTHONPATH': str(PROJECT/'src')}; env.pop('ELECTRON_RUN_AS_NODE', None)
        for key in ('QX_PROBE_FROZEN_BACKEND', 'QX_PROBE_SETTINGS_ENTRY', 'QX_PROBE_LOOPBACK',
                    'QX_PROBE_JUDGE_LOOPBACK', 'QX_PROBE_JUDGE_BUDGET', 'QX_PROBE_SETTINGS_NETWORK'):
            env.pop(key, None)
        if options.judge: env['QX_PROBE_JUDGE_BUDGET'] = 'synthetic-judge-budget-v1'
        if frozen: env['QX_PROBE_FROZEN_BACKEND'] = str(frozen)
        else:
            entry = 'synthetic_native_control_entry.py' if judge_mode else 'synthetic_native_approval_entry.py'
            env.update(QX_PROBE_SETTINGS_ENTRY=str(PROJECT/'tests/helpers'/entry),
                QX_PROBE_LOOPBACK=f'http://127.0.0.1:{server.server_port}/chat/completions',
                QX_PROBE_SETTINGS_NETWORK=str(launch/'network-tripwire.json'))
            if judge_mode: env['QX_PROBE_JUDGE_LOOPBACK'] = f'http://127.0.0.1:{server.server_port}/v1/systemone'
        command = [str(PROJECT/'desktop/node_modules/electron/dist/electron.exe'),
            str(PROJECT/'desktop/tests/model-credentials-acceptance.cjs'), '--remote-debugging-port=0',
            '--remote-debugging-address=127.0.0.1']
        report['command'] = command
        proc = subprocess.Popen(command, cwd=PROJECT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
        endpoints = Queue()
        def drain(pipe, name):
            for line in pipe:
                logs[name].append(line)
                if 'DevTools listening on ' in line: endpoints.put(line.split('DevTools listening on ', 1)[1].strip())
        Thread(target=drain, args=(proc.stdout, 'stdout'), daemon=True).start()
        Thread(target=drain, args=(proc.stderr, 'stderr'), daemon=True).start()
        def command_native(action, **values):
            request = {'id': str(uuid4()), 'action': action, **values}
            tmp = launch/'command.tmp'; tmp.write_text(json.dumps(request), encoding='utf-8'); tmp.replace(launch/'command.json')
            deadline = time.monotonic()+35
            while True:
                if (launch/'response.json').exists():
                    result = json.loads((launch/'response.json').read_text('utf-8'))
                    if result['id'] == request['id']:
                        assert 'error' not in result, result
                        return result['value']
                assert proc.poll() is None and time.monotonic() < deadline, 'TEST_COMMAND_TIMEOUT'
                time.sleep(.05)
        with sync_playwright() as pw:
            endpoint = endpoints.get(timeout=40); assert endpoint.startswith('ws://127.0.0.1:')
            browser = pw.chromium.connect_over_cdp(endpoint)
            deadline = time.monotonic()+30
            while not [p for c in browser.contexts for p in c.pages]:
                assert time.monotonic() < deadline; time.sleep(.05)
            page = [p for c in browser.contexts for p in c.pages][0]; page.set_default_timeout(25000)
            def observe(p):
                p.on('pageerror', lambda e: report['page_errors'].append(str(e)))
                p.on('request', lambda r: report['requests'].append({'method': r.method, 'url': r.url}))
                p.on('dialog', lambda d: d.accept() if d.type == 'beforeunload' else d.dismiss())
            observe(page)
            def modal():
                deadline = time.monotonic()+25
                while True:
                    found = [p for c in browser.contexts for p in c.pages if not p.is_closed() and p.url.endswith('/model-approval.html')]
                    if found:
                        result = found[0]; result.set_default_timeout(20000); observe(result)
                        expect(result.locator('#approval-confirm')).to_be_enabled(); return result
                    assert time.monotonic() < deadline; page.wait_for_timeout(50)
            def closing_action(window, action):
                try: action()
                except BrowserError:
                    # Native decisions destroy the modal before CDP may acknowledge the input.
                    if not window.is_closed(): raise
            def save(text):
                page.locator('#composer').fill(text); expect(page.locator('#save-status')).to_have_text('草稿已保存到本机')
            def settings():
                command_native('menu', label='主模型设置…'); expect(page.locator('#model-settings')).to_be_visible()
            def capability():
                return page.evaluate("async()=>{const id=location.pathname.split('/').pop();return (await fetch('/api/assistant/conversations/'+id+'/generation-capability')).json()}")
            def judge_choice(window):
                if not judge_mode: return
                expect(window.locator('#approval-judge')).to_be_visible()
                expect(window.locator('#approval-judge-select')).not_to_be_checked()
                expect(window.locator('#approval-judge')).to_contain_text('TypeSafe（api.typesafe.ai）')
                expect(window.locator('#approval-judge')).to_contain_text('同一完整文字')
                if options.judge:
                    expect(window.locator('#approval-judge-select')).to_be_enabled()
                    expect(window.locator('#approval-judge-budget')).to_contain_text('USD 0.02')
                    expect(window.locator('#approval-judge-budget')).to_contain_text('不是供应商收费上限')
                    expect(window.locator('#approval-judge-budget')).to_contain_text('实际费用尚未核对')
                else:
                    expect(window.locator('#approval-judge-select')).to_be_disabled()
                    expect(window.locator('#approval-judge-budget')).to_contain_text('仍可确认主模型发送')
            expect(page.locator('#setup')).to_be_visible()
            page.locator('#username').fill('合成确认律师'); page.locator('#password').fill('fixture123'); page.locator('#confirm').fill('fixture123')
            page.get_by_role('button', name='建立账户并打开工作台').click()
            page.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/login'), timeout=60000)
            page.get_by_label('用户名').fill('合成确认律师'); page.get_by_label('密码').fill('fixture123')
            page.get_by_role('button', name='登录', exact=True).click(); page.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/assistant'))
            save(LONG); assert capability()['state'] == 'unconfigured'; expect(page.locator('#send')).to_be_disabled()
            settings(); page.locator('#model-secret').fill(SECRET); page.locator('#model-save').click()
            expect(page.locator('#model-status')).to_contain_text('已保存'); expect(page.locator('#model-configure')).to_be_enabled()
            page.locator('#model-configure').click(); expect(page.locator('#model-runtime-status')).to_contain_text('已配置')
            if judge_mode:
                page.locator('#judge-secret').fill(JUDGE_SECRET); page.locator('#judge-save').click()
                expect(page.locator('#judge-status')).to_contain_text('已保存')
                page.locator('#judge-configure').click(); expect(page.locator('#judge-runtime-status')).to_contain_text('已配置')
            page.locator('#resume').click(); expect(page.locator('#send')).to_be_enabled()
            assert capability()['state'] == 'unapproved' and not posts
            passed('configured_saved_draft_requires_native_confirmation_without_observed_loopback_post')
            if options.profile_ui:
                from profile_ui_acceptance import run_profile_ui
                run_profile_ui(page, modal, closing_action, command_native, save, passed, posts, LONG, CONTENT)
            elif options.profile:
                from profile_approval_acceptance import run_profile
                run_profile(page, modal, closing_action, command_native, save, settings, passed, posts, LONG)
            else:
                page.locator('#send').click(); approval = modal()
                judge_choice(approval)
                assert approval.locator('#approval-content').inner_text() == LONG
                assert approval.locator('script').count() == 1, 'CONTENT_MUST_REMAIN_TEXT'
                expect(approval.locator('#approval-budget')).to_contain_text('0.024576')
                expect(approval.locator('#approval-cancel')).to_be_focused()
                assert approval.evaluate('()=>scrollY===0 && document.querySelector("#approval-budget").getBoundingClientRect().bottom<innerHeight')
                command_native('capture',target='approval',name='approval-initial.png')
                for width,height,zoom,name in [(820,740,1,'approval-100'),(760,760,1.5,'approval-150'),(640,540,2,'approval-200')]:
                    command_native('window', target='approval', width=width, height=height, zoom=zoom)
                    approval.wait_for_timeout(60)
                    assert approval.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
                    approval.locator('#approval-confirm').scroll_into_view_if_needed()
                    assert approval.locator('#approval-confirm').evaluate('el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&document.elementFromPoint(r.x+5,r.y+5)===el}')
                    command_native('capture', target='approval', name=name+'.png')
                approval.locator('#approval-cancel').focus(); closing_action(approval,lambda:approval.keyboard.press('Enter'))
                expect(page.locator('#composer')).to_have_value(LONG); expect(page.locator('#send')).to_be_enabled()
                assert not posts; assert capability()['state'] == 'unapproved'
                passed('full_text_literal_markup_small_window_scales_and_default_cancel_preserve_draft')
                save(CONTENT); expect(page.locator('#send')).to_be_enabled(); page.locator('#send').click(); approval = modal()
                judge_choice(approval)
                changed = page.evaluate("""async()=>{const url='/api/assistant/conversations/'+location.pathname.split('/').pop();
                  const v=await(await fetch(url)).json();const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('qx_csrf=')).split('=')[1]);
                  return (await fetch(url+'/draft',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
                    body:JSON.stringify({expected_scope:v.scope,expected_composer_revision:v.composer_revision,content:'另一处更新的独立合成内容'})})).status;}""")
                assert changed == 200; closing_action(approval,lambda:approval.locator('#approval-confirm').click())
                expect(page.locator('#generation-status')).to_contain_text('本次发送确认未完成')
                assert not posts
                page.reload(); expect(page.locator('#composer')).to_have_value('另一处更新的独立合成内容')
                save(CONTENT); expect(page.locator('#send')).to_be_enabled()
                passed('saved_draft_changed_during_confirmation_never_registers_or_sends_old_text')
                if frozen:
                    # Deliberately invoke only the fixed native approval API; never the sending form.
                    page.evaluate("""async()=>{const id=location.pathname.split('/').pop();const cap=await(await fetch('/api/assistant/conversations/'+id+'/generation-capability')).json();
                      window.probeApproval=null;desktopAssistant.authorizeGeneration({conversation_id:id,request_id:crypto.randomUUID(),expected_scope:cap.scope,
                        expected_composer_revision:cap.composer_revision,content_sha256:cap.content_sha256}).then(x=>window.probeApproval=x);}""")
                    approval=modal(); judge_choice(approval)
                    if options.judge: approval.locator('#approval-judge-select').check()
                    command_native('capture', target='approval', name='approval-frozen-selection.png')
                    closing_action(approval,lambda:approval.locator('#approval-confirm').click())
                    page.wait_for_function('()=>window.probeApproval!==null'); assert page.evaluate('()=>window.probeApproval') == {'ok': True}
                    assert capability()['state'] == 'ready' and not posts
                    settings()
                    if judge_mode:
                        page.locator('#judge-disable').click(); expect(page.locator('#judge-runtime-status')).to_contain_text('未配置')
                    page.locator('#model-disable').click(); expect(page.locator('#model-runtime-status')).to_contain_text('未配置')
                    page.locator('#resume').click(); assert capability()['state'] == 'unconfigured'
                    passed('frozen_private_authorization_consumes_confirmation_then_disable_without_generation_submission')
                else:
                    page.locator('#send').click(); approval=modal(); judge_choice(approval)
                    command_native('capture', target='approval', name='approval-main-only.png')
                    closing_action(approval,lambda:approval.locator('#approval-confirm').click())
                    expect(page.locator('.generation-text')).to_contain_text('独立合成候选', timeout=45000)
                    assert len(posts) == 1; expect(page.locator('#composer')).to_have_value('')
                    page.reload(); expect(page.locator('.generation-text')).to_contain_text('独立合成候选')
                    assert len(posts) == 1
                    passed('one_confirmed_send_reaches_existing_queue_loopback_receipt_and_history_reload_without_resend')
                    if judge_mode:
                        assert [p['provider'] for p in posts] == ['main']
                        passed('independent_judge_configuration_does_not_send_when_unselected_or_default_closed')
                    if options.judge:
                        save(JUDGE_CONTENT); page.locator('#send').click(); approval=modal(); judge_choice(approval)
                        assert approval.locator('#approval-content').inner_text() == JUDGE_CONTENT
                        approval.locator('#approval-judge-select').check()
                        command_native('capture', target='approval', name='approval-dual-selection.png')
                        closing_action(approval,lambda:approval.locator('#approval-confirm').click())
                        expect(page.locator('.generation-text')).to_have_count(2, timeout=45000)
                        expect(page.locator('#composer')).to_have_value('')
                        assert [p['provider'] for p in posts] == ['main', 'judge', 'main']
                        page.reload(); expect(page.locator('.generation-text')).to_have_count(2)
                        assert [p['provider'] for p in posts] == ['main', 'judge', 'main']
                        command_native('capture', name='assistant-two-synthetic-results.png')
                        passed('explicit_dual_selection_runs_judge_then_main_once_and_reload_does_not_resend')
            page.close(); report['electron_exit']=proc.wait(timeout=45); assert report['electron_exit']==0
        report['bootstrap']=json.loads((launch/'bootstrap.json').read_text('utf-8'))
        assert all(w=={'nodeIntegration':False,'contextIsolation':True,'sandbox':True,'webSecurity':True} for w in report['bootstrap']['windows'])
        assert report['page_errors']==[],report['page_errors']
        assert not report.get('provider_error'), 'UNEXPECTED_SYNTHETIC_PROVIDER_REQUEST'
        assert all(r['url'].startswith(('file:','http://127.0.0.1:')) for r in report['requests'])
        report['generation_posts']=sum(r['method']=='POST' and r['url'].endswith('/generations') for r in report['requests'])
        report['profile_generation_posts']=sum(r['method']=='POST' and r['url'].endswith('/profile-generations') for r in report['requests'])
        main_count = 0 if frozen or options.profile else 2 if options.judge else 1
        judge_count = 1 if options.judge and not frozen else 0
        assert report['generation_posts']==(0 if options.profile_ui else main_count)
        if options.profile_ui: assert report['profile_generation_posts']==1
        report['provider_order'] = [p['provider'] for p in posts]
        report['provider_posts'] = {'main': sum(p['provider']=='main' for p in posts),
            'judge': sum(p['provider']=='judge' for p in posts)}
        assert report['provider_posts'] == {'main': main_count, 'judge': judge_count}
        assert bool(report['bootstrap'].get('synthetic_judge_budget')) == options.judge
        judge_grants = [c for c in report['bootstrap'].get('judge_controls', []) if c['operation']=='authorize']
        assert len(judge_grants) == (1 if options.judge else 0), judge_grants
        assert all(c['ok'] and c['status']=='authorized' for c in judge_grants)
        if options.profile:
            grants=[c for c in report['bootstrap'].get('model_controls',[]) if c['operation']=='authorize_profile']
            assert grants==[{'operation':'authorize_profile','ok':True,'status':'authorized'}],grants
            assert not any(r['method']=='POST' and r['url'].endswith('/profile-generations') for r in report['requests'])
        if frozen or options.profile:
            assert report['bootstrap']['model_controls'][-1] == {'operation': 'disable', 'ok': True, 'status': 'disabled'}
            if judge_mode:
                assert report['bootstrap']['judge_controls'][-1] == {'operation': 'disable', 'ok': True, 'status': 'disabled'}
        if not frozen:
            report['network']=json.loads((launch/'network-tripwire.json').read_text('utf-8'))
            assert report['network'] == ({'main': main_count, 'judge': judge_count, 'blocked_other_httpx_requests': 0}
                if judge_mode else {'loopback_calls': main_count, 'external_requests': 0})
        database = data/'workspaces/main/workbench.db'
        with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as conn:
            conn.execute('PRAGMA query_only=ON')
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            report['counts']={n:conn.execute('SELECT COUNT(*) FROM '+n).fetchone()[0] for n in
                ('assistant_messages','assistant_runs','assistant_model_attempts','assistant_model_receipts','assistant_model_outputs',
                 'assistant_judge_attempts','assistant_judge_receipts','assistant_judge_decisions')}
            assert all(count == (judge_count if name.startswith('assistant_judge_') else main_count)
                for name, count in report['counts'].items()), report['counts']
            assert [r[0] for r in conn.execute('SELECT content FROM assistant_messages ORDER BY source_revision')] == (
                [] if frozen or options.profile else [CONTENT, JUDGE_CONTENT] if options.judge else [CONTENT])
            if options.profile:
                report['profile_counts']={name:conn.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
                    for name in ('assistant_profile_revisions','assistant_profile_receipts','assistant_profile_handlers','intake_cases')}
                assert not any(report['profile_counts'].values()),report['profile_counts']
            if options.profile_ui:
                report['profile_counts']={name:conn.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
                    for name in ('assistant_profile_revisions','assistant_profile_receipts','assistant_profile_handlers','intake_cases')}
                assert set(report['profile_counts'].values())=={1},report['profile_counts']
                assert conn.execute('SELECT outcome FROM assistant_profile_handlers').fetchone()[0]=='applied'
            if judge_count:
                run_id = conn.execute('SELECT run_id FROM assistant_judge_attempts').fetchone()[0]
        if judge_count:
            checked = subprocess.run([sys.executable, '-X', 'utf8', str(PROJECT/'tests/helpers/inspect_native_control_records.py'),
                str(database), '--run', run_id, '--hash', hashlib.sha256(JUDGE_CONTENT.encode()).hexdigest(),
                '--main-count', '2'], cwd=PROJECT, env={**os.environ, 'PYTHONPATH': str(PROJECT/'src')},
                capture_output=True, text=True, encoding='utf-8', check=True)
            report['judge_ledger'] = json.loads(checked.stdout)
            passed('same_run_exact_source_hash_unknown_cost_internal_unverified_judge_decision')
        for p in data.rglob('*'):
            if p.is_file():
                raw=p.read_bytes(); assert SECRET.encode() not in raw and JUDGE_SECRET.encode() not in raw,'PLAINTEXT_FILE'
        passed('protected_credentials_owned_windows_and_exact_database_counts')
        report['source_after']=hashes(); assert report['source_before']==report['source_after'],'SOURCE_DRIFT'
        report.update(status='passed',exit_code=0,loopback_posts=len(posts))
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error)); raise
    finally:
        if proc and proc.poll() is None:
            if page:
                try: page.screenshot(path=str(target/'failure.png'),full_page=True)
                except Exception: pass
            proc.terminate(); proc.wait(timeout=20)
        server.shutdown();server.server_close()
        for name,lines in logs.items():
            raw=''.join(lines);assert SECRET not in raw and JUDGE_SECRET not in raw,'PLAINTEXT_LOG'
            (launch/f'electron-{name}.txt').write_text(raw,encoding='utf-8')
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'input_files':len(report['source_before'])}))


if __name__=='__main__': main()
