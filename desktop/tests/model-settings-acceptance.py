"""Real daily Electron settings, isolated Windows vault and actual backend; no grant."""
import hashlib
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

from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
FIRST = 'synthetic-native-secret-settings-first-20261019'
SECOND = 'synthetic-native-secret-settings-second-20261019'
CONTENT = '独立合成咨询：虚构客户希望核对交货日期，尚未核实事实。'


def hashes():
    files = list((PROJECT/'src').rglob('*.py'))
    files += [p for p in (PROJECT/'desktop').iterdir() if p.suffix in ('.cjs', '.html', '.js', '.css', '.json')]
    files += [HERE/'model-settings-acceptance.py', HERE/'model-credentials-acceptance.cjs',
              PROJECT/'tests/helpers/synthetic_native_settings_entry.py']
    return {p.relative_to(PROJECT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def main():
    target = Path(sys.argv[1]).resolve(); target.mkdir(parents=True, exist_ok=False)
    frozen = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    data = target/'中文 合成设置资料'
    report = {'status': 'running', 'checks': [], 'runs': [], 'source_before': hashes(),
              'backend': 'frozen' if frozen else 'source_with_network_tripwire', 'real_model_calls': 0, 'exit_code': 1}
    if frozen:
        report['exe_sha256'] = hashlib.sha256(frozen.read_bytes()).hexdigest()
    current = None

    def passed(name):
        report['checks'].append(name); print('PASS '+name, flush=True)

    def safe_files():
        for p in data.rglob('*'):
            if p.is_file():
                raw = p.read_bytes()
                assert FIRST.encode() not in raw and SECOND.encode() not in raw, 'PLAINTEXT_FILE'

    try:
        with sync_playwright() as pw:
            class Running:
                def __init__(self, index):
                    self.dir = target/f'launch-{index}'; self.dir.mkdir()
                    self.record = {'page_errors': [], 'requests': []}; report['runs'].append(self.record)
                    env = {**os.environ, 'QX_PROBE_EVIDENCE': str(self.dir), 'QX_DESKTOP_DATA_PARENT': str(data),
                           'PYTHONPATH': str(PROJECT/'src')}
                    env.pop('ELECTRON_RUN_AS_NODE', None)
                    if frozen:
                        env['QX_PROBE_FROZEN_BACKEND'] = str(frozen)
                    else:
                        env['QX_PROBE_SETTINGS_ENTRY'] = str(PROJECT/'tests/helpers/synthetic_native_settings_entry.py')
                        env['QX_PROBE_SETTINGS_NETWORK'] = str(self.dir/'network-tripwire.json')
                    command = [str(PROJECT/'desktop/node_modules/electron/dist/electron.exe'),
                               str(HERE/'model-credentials-acceptance.cjs'), '--remote-debugging-port=0',
                               '--remote-debugging-address=127.0.0.1']
                    self.record['command'] = command
                    self.proc = subprocess.Popen(command, cwd=PROJECT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                    self.logs = {'stdout': [], 'stderr': []}; endpoints = Queue()
                    def drain(pipe, name):
                        for line in pipe:
                            self.logs[name].append(line)
                            if 'DevTools listening on ' in line:
                                endpoints.put(line.split('DevTools listening on ', 1)[1].strip())
                    Thread(target=drain, args=(self.proc.stdout, 'stdout'), daemon=True).start()
                    Thread(target=drain, args=(self.proc.stderr, 'stderr'), daemon=True).start()
                    self.endpoint = endpoints.get(timeout=40); assert self.endpoint.startswith('ws://127.0.0.1:')
                    self.browser = pw.chromium.connect_over_cdp(self.endpoint)
                    deadline = time.monotonic()+30
                    while True:
                        pages = [p for c in self.browser.contexts for p in c.pages if not p.is_closed()]
                        if pages:
                            self.page = pages[0]; break
                        assert time.monotonic() < deadline
                        time.sleep(.05)
                    self.page.set_default_timeout(25000)
                    self.page.on('pageerror', lambda e: self.record['page_errors'].append(str(e)))
                    self.page.on('request', lambda r: self.record['requests'].append({'method': r.method, 'url': r.url}))
                    self.page.on('dialog', lambda d: d.accept() if d.type == 'beforeunload' else d.dismiss())

                def command(self, action, **values):
                    request = {'id': str(uuid4()), 'action': action, **values}
                    tmp = self.dir/'command.tmp'; tmp.write_text(json.dumps(request), encoding='utf-8'); tmp.replace(self.dir/'command.json')
                    deadline = time.monotonic()+35
                    while True:
                        if (self.dir/'response.json').exists():
                            result = json.loads((self.dir/'response.json').read_text('utf-8'))
                            if result['id'] == request['id']:
                                assert 'error' not in result, result
                                return result['value']
                        assert self.proc.poll() is None and time.monotonic() < deadline, 'TEST_COMMAND_TIMEOUT'
                        time.sleep(.05)

                def recover_renderer(self, loads):
                    deadline=time.monotonic()+35
                    while True:
                        try: snapshot=json.loads((self.dir/'bootstrap.json').read_text('utf-8'))
                        except json.JSONDecodeError: snapshot={}
                        if snapshot.get('page_loads',0)>loads and snapshot.get('page_url','').startswith('file:'):
                            break
                        assert self.proc.poll() is None and time.monotonic()<deadline,'TEST_RENDERER_RECOVERY_TIMEOUT'
                        time.sleep(.05)
                    # A crashed CDP Page retains its error state; attach to the recovered native page.
                    self.browser=pw.chromium.connect_over_cdp(self.endpoint)
                    self.page=[p for c in self.browser.contexts for p in c.pages if not p.is_closed()][0]
                    self.page.set_default_timeout(25000)
                    self.page.on('pageerror',lambda e:self.record['page_errors'].append(str(e)))
                    self.page.on('request',lambda r:self.record['requests'].append({'method':r.method,'url':r.url}))
                    self.page.on('dialog',lambda d:d.accept() if d.type=='beforeunload' else d.dismiss())

                def settings(self):
                    self.command('menu', label='主模型设置…')
                    expect(self.page.locator('#model-settings')).to_be_visible()
                    expect(self.page.locator('#model-recheck')).to_be_enabled()

                def runtime(self):
                    return self.page.evaluate('()=>desktopSetup.modelRuntimeStatus()')

                def store(self, value):
                    self.page.locator('#model-secret').fill(value); self.page.locator('#model-save').click()
                    expect(self.page.locator('#model-secret')).to_have_value('')
                    expect(self.page.locator('#model-status')).to_contain_text('已保存')
                    expect(self.page.locator('#model-recheck')).to_be_enabled()

                def configure(self, model):
                    self.page.locator('#model-id').select_option(model)
                    self.page.locator('#model-configure').click()
                    expect(self.page.locator('#model-runtime-status')).to_contain_text('已配置')
                    expect(self.page.locator('#model-recheck')).to_be_enabled()
                    value = self.runtime(); assert value['ok'] and value['runtime'] == {'state': 'configured', 'model': model}, value

                def close(self):
                    if not self.page.is_closed(): self.page.close()
                    self.record['electron_exit'] = self.proc.wait(timeout=45); assert self.record['electron_exit'] == 0
                    self.record['bootstrap'] = json.loads((self.dir/'bootstrap.json').read_text('utf-8'))
                    for name, lines in self.logs.items():
                        raw = ''.join(lines); assert FIRST not in raw and SECOND not in raw, 'PLAINTEXT_LOG'
                        (self.dir/f'electron-{name}.txt').write_text(raw, encoding='utf-8')
                    assert self.record['page_errors'] == [], self.record['page_errors']
                    assert all(r['url'].startswith(('file:', 'http://127.0.0.1:')) for r in self.record['requests'])
                    if not frozen:
                        self.record['tripwire'] = json.loads((self.dir/'network-tripwire.json').read_text('utf-8'))
                        assert self.record['tripwire'] == {'httpx_calls': 0, 'external_requests': 0}
                    assert all(w == {'nodeIntegration': False, 'contextIsolation': True, 'sandbox': True, 'webSecurity': True}
                               for w in self.record['bootstrap']['windows'])
                    assert all(not c['contains_model_credential'] for c in self.record['bootstrap']['backend_configs'])
                    safe_files()

            current = Running(1); p = current.page
            expect(p.locator('#setup')).to_be_visible(); current.settings(); current.store(FIRST)
            assert current.runtime()['runtime']['state'] == 'unavailable'
            expect(p.locator('#model-configure')).to_be_disabled()
            other = current.command('other-window')
            assert other['node'] == 'undefined' and all(v.get('code') == 'ACCESS_DENIED' for k,v in other.items() if k != 'node')
            passed('stored_credential_before_account_does_not_enable_runtime_and_other_window_denied')
            p.locator('#resume').click(); expect(p.locator('#setup')).to_be_visible()
            p.locator('#username').fill('合成设置律师'); p.locator('#password').fill('fixture123'); p.locator('#confirm').fill('fixture123')
            p.get_by_role('button', name='建立账户并打开工作台').click()
            p.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/login'), timeout=60000)
            origin = p.url.rsplit('/',1)[0]
            def login():
                p.get_by_label('用户名').fill('合成设置律师'); p.get_by_label('密码').fill('fixture123')
                p.get_by_role('button', name='登录', exact=True).click(); p.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/assistant'))
            login(); p.locator('#composer').fill(CONTENT)
            expect(p.locator('#save-status')).to_have_text('草稿已保存到本机')
            conversation_url = p.url; cid = p.url.rsplit('/',1)[1]
            def capability():
                return p.evaluate("async id=>(await fetch('/api/assistant/conversations/'+id+'/generation-capability')).json()", cid)
            assert capability()['state'] == 'unconfigured'
            first_pid = json.loads((current.dir/'bootstrap.json').read_text('utf-8'))['ready']['pid']
            cookies_before = {x['name']: x['value'] for x in p.context.cookies(origin)}
            current.settings(); assert current.runtime()['runtime']['state'] == 'unconfigured'
            current.configure('deepseek-flash'); p.locator('#resume').click(); p.wait_for_url(conversation_url)
            expect(p.locator('#composer')).to_have_value(CONTENT)
            assert capability()['state'] == 'unapproved'
            assert cookies_before == {x['name']: x['value'] for x in p.context.cookies(origin)}
            assert first_pid == json.loads((current.dir/'bootstrap.json').read_text('utf-8'))['ready']['pid']
            result = p.evaluate("""async id=>{
              const cap=await(await fetch('/api/assistant/conversations/'+id+'/generation-capability')).json();
              const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('qx_csrf=')).split('=')[1]);
              const response=await fetch('/api/assistant/conversations/'+id+'/generations',{method:'POST',headers:{
                'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({request_id:crypto.randomUUID(),
                expected_scope:cap.scope,expected_composer_revision:cap.composer_revision,content:document.querySelector('#composer').value})});
              return {status:response.status};
            }""", cid)
            assert result['status'] == 403, result
            passed('configure_keeps_pid_login_and_draft_but_capability_unapproved_and_post_forbidden')
            denied = p.evaluate("async()=>({runtime:await desktopSetup.modelRuntimeStatus(),configure:await desktopSetup.modelConfigure('deepseek-flash'),disable:await desktopSetup.modelDisable()})")
            assert all(v.get('code') == 'ACCESS_DENIED' for v in denied.values())
            current.settings(); current.configure('deepseek-v4-pro')
            expect(p.locator('#model-runtime-status')).to_contain_text('尚未授权')
            current.store(SECOND); assert current.runtime()['runtime']['state'] == 'unconfigured'
            current.configure('deepseek-flash'); p.locator('#model-disable').click()
            expect(p.locator('#model-recheck')).to_be_enabled(); assert current.runtime()['runtime']['state'] == 'unconfigured'
            current.configure('deepseek-flash'); p.locator('#model-remove').click()
            expect(p.locator('#model-recheck')).to_be_enabled()
            assert p.evaluate('()=>desktopSetup.modelStatus()')['status'] == 'empty'
            assert current.runtime()['runtime']['state'] == 'unconfigured'
            current.store(FIRST); current.configure('deepseek-flash')
            passed('switch_disable_replace_and_remove_use_native_control_without_a_send_grant')
            for width,height,zoom,name in [(1240,850,1,'settings-configured'),(760,760,1.5,'settings-150-percent'),(640,540,2,'settings-200-percent')]:
                metrics=current.command('window',width=width,height=height,zoom=zoom)
                p.wait_for_function('(w)=>Math.abs(innerWidth-w)<2',arg=metrics['width']/metrics['zoom'])
                p.evaluate('()=>{scrollTo(0,0);return new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))}')
                assert p.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
                current.command('capture',name=name+'.png')
                p.locator('#model-configure').scroll_into_view_if_needed()
                assert p.locator('#model-configure').evaluate('el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&document.elementFromPoint(r.x+5,r.y+5)===el}')
                current.command('capture',name=name+'-controls.png')
            current.close(); current=None
            passed('actual_windows_settings_layout_at_100_150_200_percent_and_clean_shutdown')
            current=Running(2);p=current.page
            p.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/login'),timeout=60000);login()
            current.settings();assert current.runtime()['runtime']['state']=='unconfigured'
            assert p.evaluate('()=>desktopSetup.modelStatus()')['status']=='saved'
            current.configure('deepseek-flash')
            current.command('stop-backend');expect(p.locator('#retry')).to_be_visible()
            denied=p.evaluate('()=>desktopSetup.modelRuntimeStatus()');assert denied.get('code')=='ACCESS_DENIED',denied
            p.locator('#retry').click();p.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/login'),timeout=60000);login()
            current.settings();assert current.runtime()['runtime']['state']=='unconfigured'
            passed('restart_retains_ciphertext_only_and_owned_backend_failure_clears_runtime')
            current.configure('deepseek-flash')
            crashed=current.command('crash-renderer');current.recover_renderer(crashed['loads']);p=current.page
            expect(p.locator('#retry')).to_be_visible()
            stopped=json.loads((current.dir/'bootstrap.json').read_text('utf-8'))
            assert stopped['backend_exit']['code']==0,stopped['backend_exit']
            current.settings();current.store(SECOND);assert current.runtime()['runtime']['state']=='unavailable'
            p.locator('#resume').click();p.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/login'),timeout=60000);login()
            passed('renderer_crash_stops_configured_backend_before_credential_replacement')
            current.command('menu',label='备份案件资料…');expect(p.locator('#maintenance')).to_be_visible()
            p.locator('#resume').click();p.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/login'),timeout=60000);login()
            current.settings();assert current.runtime()['runtime']['state']=='unconfigured'
            current.close();current=None
            passed('backup_maintenance_still_stops_backend_and_resume_starts_unconfigured')
            with sqlite3.connect(data/'workspaces/main/workbench.db') as conn:
                report['integrity']=conn.execute('PRAGMA integrity_check').fetchone()[0];assert report['integrity']=='ok'
                report['counts']={name:conn.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
                    ('assistant_messages','assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
                assert all(n==0 for n in report['counts'].values()),report['counts']
            passed('zero_model_records_no_plaintext_leak_and_no_external_request')
            report['source_after']=hashes();assert report['source_before']==report['source_after']
            report.update(status='passed',exit_code=0)
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error));raise
    finally:
        if current and current.proc.poll() is None:
            try:current.page.screenshot(path=str(target/'failure.png'),full_page=True)
            except Exception:pass
            current.proc.terminate();current.proc.wait(timeout=20)
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'input_files':len(report['source_before'])}))


if __name__=='__main__':
    main()
