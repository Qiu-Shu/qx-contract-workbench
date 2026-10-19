"""Actual native confirmation, source loopback or frozen grant-without-send.

Uses the existing actual-main observer. All accounts/text/credentials are synthetic.
No test provider is packaged and the frozen path never submits an approved POST.
"""
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
CONTENT = '独立合成咨询：虚构客户希望核对交货日期，尚未核实事实。'
LONG = '<script>禁止执行合成标记</script>\n' + '独立合成材料；客户陈述尚未核实，需要律师核对时间及原件。\n' * 110


def hashes():
    result = subprocess.run(['git', 'ls-files', '-z', '-co', '--exclude-standard', '--', 'src', 'desktop',
        'tests', 'scripts', 'config', 'schemas', 'pyproject.toml', 'requirements.lock'], cwd=PROJECT,
        capture_output=True, check=True)
    return {p: hashlib.sha256((PROJECT/p).read_bytes()).hexdigest() for p in
        sorted(set(result.stdout.decode('utf-8').split('\0'))-{''}) if (PROJECT/p).is_file()}


def main():
    target = Path(sys.argv[1]).resolve(); target.mkdir(parents=True, exist_ok=False)
    frozen = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    data = target/'中文 合成确认资料'; launch = target/'launch'; launch.mkdir()
    report = {'status': 'running', 'checks': [], 'source_before': hashes(), 'real_model_calls': 0,
        'backend': 'frozen_grant_without_send' if frozen else 'source_loopback', 'exit_code': 1,
        'page_errors': [], 'requests': []}
    if frozen: report['exe_sha256'] = hashlib.sha256(frozen.read_bytes()).hexdigest()
    posts = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            try:
                assert self.path == '/chat/completions'
                assert self.headers['Authorization'] == 'Bearer '+SECRET
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                source = json.loads(body['messages'][1]['content'])
                assert source['content'] == CONTENT
                posts.append({'content_sha256': hashlib.sha256(CONTENT.encode()).hexdigest()})
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
        if frozen: env['QX_PROBE_FROZEN_BACKEND'] = str(frozen)
        else:
            env.update(QX_PROBE_SETTINGS_ENTRY=str(PROJECT/'tests/helpers/synthetic_native_approval_entry.py'),
                QX_PROBE_LOOPBACK=f'http://127.0.0.1:{server.server_port}/chat/completions',
                QX_PROBE_SETTINGS_NETWORK=str(launch/'network-tripwire.json'))
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
            page.locator('#resume').click(); expect(page.locator('#send')).to_be_enabled()
            assert capability()['state'] == 'unapproved' and not posts
            passed('configured_saved_draft_requires_native_confirmation_without_network_call')
            page.locator('#send').click(); approval = modal()
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
                approval=modal(); closing_action(approval,lambda:approval.locator('#approval-confirm').click())
                page.wait_for_function('()=>window.probeApproval!==null'); assert page.evaluate('()=>window.probeApproval') == {'ok': True}
                assert capability()['state'] == 'ready' and not posts
                settings(); page.locator('#model-disable').click(); expect(page.locator('#model-runtime-status')).to_contain_text('未配置')
                page.locator('#resume').click(); assert capability()['state'] == 'unconfigured'
                passed('frozen_private_authorization_consumes_confirmation_then_disable_without_any_provider_post')
            else:
                page.locator('#send').click(); approval=modal(); closing_action(approval,lambda:approval.locator('#approval-confirm').click())
                expect(page.locator('.generation-text')).to_contain_text('独立合成候选', timeout=45000)
                assert len(posts) == 1; expect(page.locator('#composer')).to_have_value('')
                page.reload(); expect(page.locator('.generation-text')).to_contain_text('独立合成候选')
                assert len(posts) == 1
                passed('one_confirmed_send_reaches_existing_queue_loopback_receipt_and_history_reload_without_resend')
            page.close(); report['electron_exit']=proc.wait(timeout=45); assert report['electron_exit']==0
        report['bootstrap']=json.loads((launch/'bootstrap.json').read_text('utf-8'))
        assert all(w=={'nodeIntegration':False,'contextIsolation':True,'sandbox':True,'webSecurity':True} for w in report['bootstrap']['windows'])
        assert report['page_errors']==[],report['page_errors']
        assert all(r['url'].startswith(('file:','http://127.0.0.1:')) for r in report['requests'])
        report['generation_posts']=sum(r['method']=='POST' and r['url'].endswith('/generations') for r in report['requests'])
        assert report['generation_posts']==(0 if frozen else 1)
        if not frozen:
            report['network']=json.loads((launch/'network-tripwire.json').read_text('utf-8'))
            assert report['network']=={'loopback_calls':1,'external_requests':0}
        with sqlite3.connect(data/'workspaces/main/workbench.db') as conn:
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            report['counts']={n:conn.execute('SELECT COUNT(*) FROM '+n).fetchone()[0] for n in
                ('assistant_messages','assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
            assert set(report['counts'].values())==({0} if frozen else {1}),report['counts']
        for p in data.rglob('*'):
            if p.is_file(): assert SECRET.encode() not in p.read_bytes(),'PLAINTEXT_FILE'
        passed('protected_credentials_no_external_requests_owned_windows_and_exact_database_counts')
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
            raw=''.join(lines);assert SECRET not in raw,'PLAINTEXT_LOG'
            (launch/f'electron-{name}.txt').write_text(raw,encoding='utf-8')
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'input_files':len(report['source_before'])}))


if __name__=='__main__': main()
