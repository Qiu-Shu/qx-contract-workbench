"""Actual Windows Electron/OS vault acceptance, only independent synthetic markers."""
import hashlib
import json
import os
from pathlib import Path
from queue import Queue
import re
import socket
import sqlite3
import subprocess
import sys
from threading import Thread
import time
from uuid import uuid4

from playwright.sync_api import sync_playwright, expect

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
FIRST = 'synthetic-native-secret-first-independent-20261019'
SECOND = 'synthetic-native-secret-second-independent-20261019'
INPUTS = ['desktop/'+name for name in ('main.cjs','backend.cjs','maintenance.cjs','policy.cjs',
    'preload.cjs','setup.html','setup.js','setup.css','model-settings.cjs','model-credentials.cjs','package.json')]

def hashes():
    return {name:hashlib.sha256((PROJECT/name).read_bytes()).hexdigest() for name in INPUTS}

def main():
    target = Path(sys.argv[1]).resolve();target.mkdir(parents=True,exist_ok=False)
    data = target/'中文 合成桌面';vault=data/'model-credentials/deepseek.bin'
    report={'status':'running','checks':[],'runs':[],'source_before':hashes(),'real_model_calls':0,'exit_code':1}
    current=None
    def passed(name):report['checks'].append(name);print('PASS '+name,flush=True)
    def safe_files():
        for path in data.rglob('*'):
            if path.is_file():
                raw=path.read_bytes()
                assert FIRST.encode() not in raw and SECOND.encode() not in raw, 'PLAINTEXT_IN_DESKTOP_FILE'
    try:
        with sync_playwright() as pw:
            class Running:
                def __init__(self,index):
                    self.dir=target/f'launch-{index}';self.dir.mkdir()
                    self.record={'page_errors':[],'requests':[]};report['runs'].append(self.record)
                    env={**os.environ,'QX_PROBE_EVIDENCE':str(self.dir),'QX_DESKTOP_DATA_PARENT':str(data),'PYTHONPATH':str(PROJECT/'src')}
                    env.pop('ELECTRON_RUN_AS_NODE',None)
                    command=[str(PROJECT/'desktop/node_modules/electron/dist/electron.exe'),str(HERE/'model-credentials-acceptance.cjs'),
                        '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1']
                    self.record['command']=command
                    self.proc=subprocess.Popen(command,cwd=PROJECT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
                    self.stdout=[];self.stderr=[];endpoints=Queue()
                    def drain(pipe,lines,scan=False):
                        for line in pipe:
                            lines.append(line)
                            if scan and 'DevTools listening on ' in line:endpoints.put(line.split('DevTools listening on ',1)[1].strip())
                    Thread(target=drain,args=(self.proc.stderr,self.stderr,True),daemon=True).start()
                    Thread(target=drain,args=(self.proc.stdout,self.stdout),daemon=True).start()
                    endpoint=endpoints.get(timeout=40);assert endpoint.startswith('ws://127.0.0.1:')
                    self.browser=pw.chromium.connect_over_cdp(endpoint)
                    deadline=time.monotonic()+30
                    while True:
                        pages=[p for c in self.browser.contexts for p in c.pages if not p.is_closed()]
                        if pages:self.page=pages[0];break
                        assert time.monotonic()<deadline
                        time.sleep(.05)
                    self.page.set_default_timeout(20000)
                    self.page.on('pageerror',lambda e:self.record['page_errors'].append(str(e)))
                    self.page.on('request',lambda r:self.record['requests'].append({'method':r.method,'url':r.url}))
                    self.page.on('dialog',lambda d:d.accept() if d.type=='beforeunload' else d.dismiss())
                def command(self,action,**values):
                    request={'id':str(uuid4()),'action':action,**values}
                    tmp=self.dir/'command.tmp';tmp.write_text(json.dumps(request),encoding='utf-8');tmp.replace(self.dir/'command.json')
                    deadline=time.monotonic()+30
                    while True:
                        if (self.dir/'response.json').exists():
                            result=json.loads((self.dir/'response.json').read_text('utf-8'))
                            if result['id']==request['id']:
                                assert 'error' not in result,result;return result['value']
                        assert self.proc.poll() is None and time.monotonic()<deadline,'TEST_MENU_TIMEOUT'
                        self.page.wait_for_timeout(50)
                def open_settings(self):
                    self.command('menu',label='主模型设置…')
                    expect(self.page.locator('#model-settings')).to_be_visible()
                    expect(self.page.locator('#model-save')).to_be_enabled()
                def status(self):return self.page.evaluate('()=>desktopSetup.modelStatus()')
                def store(self,secret):
                    self.page.locator('#model-secret').fill(secret)
                    self.page.locator('#model-save').click()
                    expect(self.page.locator('#model-secret')).to_have_value('')
                    expect(self.page.locator('#model-status')).to_contain_text('已保存')
                    expect(self.page.locator('#model-save')).to_be_enabled()
                    assert self.status()=={'status':'saved'}
                def close(self):
                    if not self.page.is_closed():self.page.close()
                    self.record['electron_exit']=self.proc.wait(timeout=40)
                    assert self.record['electron_exit']==0
                    self.record['bootstrap']=json.loads((self.dir/'bootstrap.json').read_text('utf-8'))
                    for name,lines in [('stdout',self.stdout),('stderr',self.stderr)]:
                        raw=''.join(lines);assert FIRST not in raw and SECOND not in raw,'PLAINTEXT_IN_PROCESS_LOG'
                        (self.dir/f'electron-{name}.txt').write_text(raw,encoding='utf-8')
                    assert self.record['page_errors']==[],self.record['page_errors']
                    assert all(item['url'].startswith(('file:','http://127.0.0.1:')) for item in self.record['requests'])
                    assert all(w=={'nodeIntegration':False,'contextIsolation':True,'sandbox':True,'webSecurity':True} for w in self.record['bootstrap']['windows'])
                    assert 'actual_will_quit' in self.record['bootstrap']['events']
                    safe_files()
            current=Running(1);p=current.page
            expect(p.locator('#setup')).to_be_visible()
            denied=p.evaluate("async()=>({status:await desktopSetup.modelStatus(),save:await desktopSetup.modelSave('synthetic-native-secret-wrong-mode'),remove:await desktopSetup.modelRemove()})")
            assert all(v.get('code')=='ACCESS_DENIED' for v in denied.values()),denied
            assert not vault.exists();passed('setup_wrong_mode_cannot_read_or_mutate_credentials')
            current.open_settings();assert current.status()=={'status':'empty'}
            current.store(FIRST);first_cipher=vault.read_bytes();assert FIRST.encode() not in first_cipher
            passed('actual_native_settings_saves_only_windows_protected_ciphertext')
            other=current.command('other-window')
            assert other['node']=='undefined' and all(other[k].get('code')=='ACCESS_DENIED' for k in ('status','save','remove')),other
            assert vault.read_bytes()==first_cipher
            passed('second_sandboxed_window_with_real_preload_denied_by_original_window_guard')
            current.store(SECOND);assert vault.read_bytes()!=first_cipher
            metrics=current.command('window',width=760,height=760,zoom=1.5)
            p.wait_for_function('(expected)=>Math.abs(innerWidth-expected)<2',arg=metrics['width']/metrics['zoom'])
            p.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            size=p.evaluate('()=>({width:innerWidth,scroll:document.documentElement.scrollWidth})')
            assert size['scroll']<=size['width']+1,size
            report['zoom_viewport']={**metrics,**size}
            current.command('capture',name='settings-150-percent.png')
            p.locator('#model-save').scroll_into_view_if_needed()
            controls=p.locator('#model-save').evaluate("el=>{const r=el.getBoundingClientRect();return {visible:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,hit:document.elementFromPoint(r.left+5,r.top+5)===el}}")
            assert controls['visible'] and controls['hit'],controls
            current.command('capture',name='settings-150-percent-controls.png')
            metrics=current.command('window',width=1240,height=850,zoom=1)
            p.wait_for_function('(expected)=>Math.abs(innerWidth-expected)<2',arg=metrics['width'])
            p.evaluate('()=>{window.scrollTo(0,0);return new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))}')
            current.command('capture',name='settings-saved.png')
            current.close();current=None
            passed('replace_then_clean_exit_keeps_ciphertext_and_supports_small_zoomed_window')

            current=Running(2);p=current.page;expect(p.locator('#setup')).to_be_visible()
            current.open_settings();assert current.status()=={'status':'saved'}
            passed('real_electron_restart_reads_existing_windows_protected_credential')
            p.locator('#model-secret').fill(FIRST)
            p.locator('#resume').click();expect(p.locator('#setup')).to_be_visible()
            expect(p.locator('#model-secret')).to_have_value('')
            p.locator('#username').fill('合成凭据律师');p.locator('#password').fill('fixture123');p.locator('#confirm').fill('fixture123')
            p.get_by_role('button',name='建立账户并打开工作台').click()
            p.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/login'),timeout=60000);origin=p.url.rsplit('/',1)[0]
            p.get_by_label('用户名').fill('合成凭据律师');p.get_by_label('密码').fill('fixture123');p.get_by_role('button',name='登录',exact=True).click()
            p.wait_for_url(origin+'/assistant');p.locator('#composer').fill('独立合成：保存凭据不授予生成权限。')
            expect(p.locator('#save-status')).to_have_text('草稿已保存到本机')
            expect(p.locator('#send')).to_be_disabled()
            cid=p.url.rsplit('/',1)[1]
            capability=p.evaluate("async id=>(await fetch('/api/assistant/conversations/'+id+'/generation-capability')).json()",cid)
            assert capability['state']=='unconfigured',capability
            denied=p.evaluate("async()=>({status:await desktopSetup.modelStatus(),save:await desktopSetup.modelSave('synthetic-native-secret-untrusted-http'),remove:await desktopSetup.modelRemove()})")
            assert all(v.get('code')=='ACCESS_DENIED' for v in denied.values()),denied
            passed('credential_save_does_not_enable_generation_or_expose_native_mutations_to_backend_page')
            current.open_settings()
            with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',int(origin.rsplit(':',1)[1])))!=0
            cipher=vault.read_bytes();vault.write_bytes(b'independent synthetic corrupt ciphertext')
            p.reload();expect(p.locator('#model-settings')).to_be_visible()
            assert current.status()['status']=='invalid'
            assert vault.read_bytes()==b'independent synthetic corrupt ciphertext'
            expect(p.locator('#model-validation')).to_contain_text('无法读取')
            current.command('capture',name='settings-corrupt.png')
            passed('stopped_owned_backend_and_corrupt_credential_reported_without_silent_rewrite')
            p.locator('#model-remove').click();expect(p.locator('#model-status')).to_contain_text('已移除')
            assert not vault.exists() and current.status()=={'status':'empty'}
            current.close();current=None;passed('explicit_remove_deletes_only_selected_native_credential')
            db=data/'workspaces/main/workbench.db'
            with sqlite3.connect(db) as conn:
                report['counts']={name:conn.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
                    ('assistant_messages','assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
                assert all(n==0 for n in report['counts'].values())
            assert not (data/'desktop-settings.json').exists() or b'synthetic-native-secret-' not in (data/'desktop-settings.json').read_bytes()
            for run in report['runs']:
                assert all(not c['contains_model_credential'] and not any('model' in k or 'secret' in k or 'key' in k for k in c['keys']) for c in run['bootstrap']['backend_configs'])
            passed('no_plaintext_in_desktop_files_logs_or_backend_stdin_and_zero_model_attempts')
            report['source_after']=hashes();assert report['source_before']==report['source_after']
            report.update(status='passed',exit_code=0)
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error));raise
    finally:
        if current and current.proc.poll() is None:
            try:current.page.screenshot(path=str(target/'failure.png'),full_page=True)
            except Exception:pass
            current.proc.terminate();current.proc.wait(timeout=15)
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'source_unchanged':True}))

if __name__=='__main__':main()
