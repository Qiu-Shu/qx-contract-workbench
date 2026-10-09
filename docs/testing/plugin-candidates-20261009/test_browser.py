from pathlib import Path
import socket,time,json
import httpx
from tests.integration.test_plugin_candidates import input_body
from threading import Thread
import uvicorn
from playwright.sync_api import sync_playwright, expect
from tests.integration.test_case_bridge import selected
from tests.integration.test_assisted_review import assisted_api


def test_browser_consent_and_revoke(selected, monkeypatch):
    client, _, _, _, path, matter, _, _ = selected
    body = input_body(selected)
    root = Path.cwd()
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(root / '.local/scrapling/browsers'))
    sock=socket.socket();sock.bind(('127.0.0.1',18768))
    server=uvicorn.Server(uvicorn.Config(client.app,host='127.0.0.1',port=18768,lifespan='off',access_log=False,log_level='error'))
    thread=Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':k,'value':v,'url':'http://127.0.0.1:18768'} for k,v in client.cookies.items()])
            page=context.new_page();errors=[];external=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            def route(req):
                if not req.request.url.startswith('http://127.0.0.1:18768/'):
                    external.append(req.request.url);req.abort()
                else:req.continue_()
            page.route('**/*',route)
            page.goto('http://127.0.0.1:18768/matters/'+matter+'/review')
            expect(page.locator('#candidate-opinion-anchor option')).not_to_have_count(0)
            expect(page.locator('[name=allow_candidate_submission]')).not_to_be_checked()
            page.locator('[name=share_with_chat]').check()
            page.get_by_role('button',name='开放所选连接权限',exact=True).click()
            try: expect(page.locator('#case-bridge-status')).to_contain_text('本案只读连接已开放')
            except AssertionError:
                print({'message':page.locator('#message').inner_text(),'errors':errors})
                raise
            assert path.is_file()
            with httpx.Client(trust_env=False) as http:
                auth={'Authorization':'Bearer '+json.loads(path.read_text(encoding='utf8'))['token']}
                assert http.post('http://127.0.0.1:18768/api/case-bridge/candidates',headers=auth,json=body).status_code==403
            page.locator('[name=share_with_chat]').check()
            page.locator('[name=allow_candidate_submission]').check()
            page.get_by_role('button',name='开放所选连接权限',exact=True).click()
            expect(page.locator('#case-bridge-status')).to_contain_text('本案读取及一轮候选提交已开放')
            with httpx.Client(trust_env=False) as http:
                auth={'Authorization':'Bearer '+json.loads(path.read_text(encoding='utf8'))['token']}
                result=http.post('http://127.0.0.1:18768/api/case-bridge/candidates',headers=auth,json=body)
                assert result.status_code==201,result.text
            page.reload()
            expect(page.locator('#candidate-opinion-list')).to_contain_text('本轮候选已保存')
            expect(page.locator('#findings')).to_contain_text('模型来源未核验')
            expect(page.locator('#case-bridge-open')).to_be_disabled()
            page.screenshot(path=str(root/'.audit-local/plugin-candidates-20261009/browser-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(root/'.audit-local/plugin-candidates-20261009/browser-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.get_by_role('button',name='撤销本次连接',exact=True).click()
            expect(page.locator('#case-bridge-status')).to_contain_text('本次连接已撤销')
            assert not path.exists()
            assert errors==[] and external==[]
            browser.close()
    finally:
        server.should_exit=True;thread.join(10);sock.close();assert not thread.is_alive()
