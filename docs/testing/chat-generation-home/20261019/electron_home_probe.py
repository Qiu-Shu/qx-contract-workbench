"""Drive the real Electron main window over loopback CDP, using an isolated workspace."""
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

from playwright.sync_api import sync_playwright, expect

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
TEXT='独立合成Electron验收：请列出虚构交货日期的待核事项。'
OUTPUT='独立合成Electron候选：交货日期仍需律师核对消息原文。'
INPUTS=['desktop/main.cjs','desktop/backend.cjs','desktop/preload.cjs','desktop/policy.cjs',
    'desktop/setup.js','src/cn_contract/desktop_entry.py','src/cn_contract/web/assistant_generation.py',
    'src/cn_contract/assistant/providers/history.py','src/cn_contract/domain.py',
    'src/cn_contract/web/templates/assistant.html','src/cn_contract/web/static/assistant.css',
    *['src/cn_contract/web/static/'+name for name in ('assistant.mjs','assistant-api.mjs',
        'assistant-state.mjs','assistant-generation.mjs','assistant-render.mjs','assistant-composer.mjs','assistant-materials.mjs')]]

def hashes():
    return {name:hashlib.sha256((PROJECT/name).read_bytes()).hexdigest() for name in INPUTS}

def main():
    mode=sys.argv[1]
    assert mode in ('default','synthetic','frozen')
    target=Path(sys.argv[2]).resolve();target.mkdir(parents=True,exist_ok=False)
    report={'scope':'actual development Electron main/BrowserWindow/preload; not installed app acceptance',
        'mode':mode,'checks':[],'page_errors':[],'requests':[],'source_before':hashes(),'exit_code':1,'real_model_calls':0}
    env={**os.environ,'QX_PROBE_MODE':mode,'QX_PROBE_EVIDENCE':str(target),
        'QX_DESKTOP_DATA_PARENT':str(target/'合成 Electron 资料'),'PYTHONPATH':str(PROJECT/'src')}
    env.pop('ELECTRON_RUN_AS_NODE',None)
    if mode=='frozen':env['QX_PROBE_FROZEN_EXE']=str(Path(sys.argv[3]).resolve())
    command=[str(PROJECT/'desktop/node_modules/electron/dist/electron.exe'),str(HERE/'electron_probe_bootstrap.cjs'),
        '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1']
    report['command']=command
    process=subprocess.Popen(command,cwd=PROJECT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
    events=Queue();stderr=[];stdout=[]
    def drain(pipe,output,scan=False):
        for line in pipe:
            output.append(line)
            if scan and 'DevTools listening on ' in line:events.put(line.split('DevTools listening on ',1)[1].strip())
    Thread(target=drain,args=(process.stderr,stderr,True),daemon=True).start()
    Thread(target=drain,args=(process.stdout,stdout),daemon=True).start()
    def passed(name):
        report['checks'].append(name);print('PASS '+name,flush=True)
    try:
        endpoint=events.get(timeout=40);assert endpoint.startswith('ws://127.0.0.1:')
        with sync_playwright() as playwright:
            browser=playwright.chromium.connect_over_cdp(endpoint)
            page=None;deadline=time.monotonic()+30
            while page is None:
                pages=[item for context in browser.contexts for item in context.pages if not item.is_closed()]
                if pages:page=pages[0]
                else:
                    assert time.monotonic()<deadline,'actual Electron BrowserWindow missing'
                    time.sleep(.05)
            page.set_default_timeout(20000);expect.set_options(timeout=20000)
            page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            page.on('request',lambda request:report['requests'].append({'method':request.method,'url':request.url}))
            page.on('dialog',lambda dialog:dialog.accept() if dialog.type=='beforeunload' else dialog.dismiss())
            expect(page.locator('#setup')).to_be_visible()
            credentials={'username':'合成Electron律师','password':'fixture123'}
            page.locator('#username').fill(credentials['username']);page.locator('#password').fill(credentials['password'])
            page.locator('#confirm').fill(credentials['password']);page.get_by_role('button',name='建立账户并打开工作台').click()
            page.wait_for_url(re.compile(r'http://127\.0\.0\.1:\d+/login'),timeout=60000)
            origin=page.url.rsplit('/',1)[0]
            page.get_by_label('用户名').fill(credentials['username']);page.get_by_label('密码').fill(credentials['password'])
            page.get_by_role('button',name='登录',exact=True).click();page.wait_for_url(origin+'/assistant')
            page.wait_for_function("document.getElementById('account-name').textContent.includes('合成Electron律师')")
            bootstrap=json.loads((target/'bootstrap.json').read_text('utf-8'))
            assert bootstrap['window']=={'nodeIntegration':False,'contextIsolation':True,'sandbox':True,
                'webSecurity':True}
            exposed=page.evaluate("async()=>({node:typeof require,process:typeof process,setupState:await window.desktopSetup.state()})")
            assert exposed=={'node':'undefined','process':'undefined','setupState':None},exposed
            passed('actual_main_provision_login_home_and_original_sandbox_preload_policy')
            page.locator('#composer').fill(TEXT);expect(page.locator('#save-status')).to_have_text('草稿已保存到本机')
            conversation=page.url.split('/')[-1];assert conversation!='assistant'
            if mode=='synthetic':
                expect(page.locator('#send')).to_be_enabled();page.locator('#send').click()
                expect(page.locator('#history .message-text').last).to_have_text(TEXT)
                expect(page.locator('.generation-text').last).to_have_text(OUTPUT)
                expect(page.locator('.generation-result').last).to_contain_text('内部草稿 · 待核对')
                assert page.locator('#composer').input_value()==''
                passed('actual_electron_send_one_message_and_render_internal_candidate')
                page.reload();expect(page.locator('.generation-text').last).to_have_text(OUTPUT)
                page.locator('.generation-text').last.evaluate("el=>el.scrollIntoView({block:'start'})")
                visible=page.locator('.generation-text').last.evaluate("""el=>{
                  const r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.left+30,r.top+Math.min(10,r.height/2));
                  return {top:r.top,bottom:r.bottom,viewport:innerHeight,uncovered:hit===el || el.contains(hit)};
                }""")
                assert visible['uncovered'] and visible['top']>=0 and visible['bottom']<=visible['viewport'],visible
                report['candidate_visible_after_scroll']=visible
                page.screenshot(path=str(target/'electron-candidate-visible.png'),full_page=False)
                runtime=json.loads((target/'synthetic-runtime.json').read_text('utf-8'))
                assert len(runtime['received'])==1 and runtime['errors']==[]
                passed('actual_electron_reload_recovers_authorized_history_without_provider_replay')
            else:
                expect(page.locator('#send')).to_be_disabled()
                expect(page.locator('#generation-note')).to_contain_text('未配置')
                result=page.evaluate("""async cid=>{
                  const base='/api/assistant/conversations/'+encodeURIComponent(cid);
                  const view=await (await fetch(base)).json();
                  const cap=await (await fetch(base+'/generation-capability')).json();
                  const h=await fetch(base+'/generation-history?message_id='+crypto.randomUUID());
                  const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('qx_csrf=')).slice(8));
                  const send=await fetch(base+'/generations',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({request_id:crypto.randomUUID(),expected_scope:view.scope,expected_composer_revision:view.composer_revision,content:view.draft_input})});
                  return {capability:cap.state,historyStatus:h.status,deniedStatus:send.status,denied:await send.json()};
                }""",conversation)
                assert result['capability']=='unconfigured' and result['deniedStatus']==403 and result['denied']['code']=='BLOCKED_LIVE',result
                # Invalid/foreign IDs are rejected; endpoint presence differs from a missing route.
                assert result['historyStatus']==403,result
                assert page.locator('#composer').input_value()==TEXT
                passed('actual_electron_default_closed_and_new_history_route_authenticated')
            awaitless=page.evaluate("async()=>await window.desktopSetup.start({username:'must-not-create',password:'fixture123'})")
            assert awaitless=={'ok':False}
            assert report['page_errors']==[],report['page_errors']
            assert all(item['url'].startswith(('file:',origin)) for item in report['requests']),report['requests']
            page.screenshot(path=str(target/'electron-home.png'),full_page=True)
            passed('renderer_cannot_provision_workspace_and_no_external_browser_requests')
            page.close()
        report['electron_exit']=process.wait(timeout=40)
        assert report['electron_exit']==0
        bootstrap=json.loads((target/'bootstrap.json').read_text('utf-8'))
        assert bootstrap['backend_exit']['code']==0,bootstrap
        assert 'actual_app_will_quit' in bootstrap['events']
        with socket.socket() as sock:
            assert sock.connect_ex(('127.0.0.1',bootstrap['ready']['port']))!=0,'backend port left open'
        database=target/'合成 Electron 资料/workspaces/main/workbench.db'
        with sqlite3.connect(database) as db:
            counts={name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
                ('assistant_messages','assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
            assert db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
        assert list(counts.values())==([1,1,1,1] if mode=='synthetic' else [0,0,0,0]),counts
        report['counts']=counts;passed('actual_app_quit_stops_owned_backend_and_sqlite_counts_match')
        report['source_after']=hashes();report['source_unchanged']=report['source_before']==report['source_after']
        report['status']='passed';report['exit_code']=0
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error));raise
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
        report['process_returncode']=process.returncode
        (target/'electron-stderr.txt').write_text(''.join(stderr),encoding='utf-8')
        (target/'electron-stdout.txt').write_text(''.join(stdout),encoding='utf-8')
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'source_unchanged':report['source_unchanged']},ensure_ascii=False))

if __name__=='__main__':main()
