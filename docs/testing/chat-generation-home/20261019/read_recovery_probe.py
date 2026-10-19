import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from ui_fixture import ui_fixture
from browser_probe import CHROMIUM,hashes

target=Path(sys.argv[1]);target.mkdir(parents=True,exist_ok=False)
report={'exit_code':1,'checks':[],'source_before':hashes()}
try:
    with ui_fixture(target) as f,sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(CHROMIUM),headless=True)
        page=browser.new_page();page.set_default_timeout(4000)
        page.goto(f.origin+'/login');page.get_by_label('用户名').fill(f.credentials['username'])
        page.get_by_label('密码').fill(f.credentials['password']);page.get_by_role('button',name='登录',exact=True).click()
        page.wait_for_url(f.origin+'/assistant')
        calls=[]
        def fail_once(route):
            calls.append(route.request.url)
            route.fulfill(status=503,content_type='application/json',body='{"error":{"code":"REQUEST_FAILED"}}')
        pattern='**/generation-capability'
        page.route(pattern,fail_once)
        page.locator('#composer').fill(f.texts['first'])
        expect(page.locator('#generation-status')).to_contain_text('刷新')
        page.wait_for_timeout(350)
        assert len(calls)==1,'failed read must not loop'
        expect(page.locator('#refresh-run')).to_be_visible()
        if len(sys.argv)>2:
            page.screenshot(path=str(target/'retry-visible.png'))
        page.unroute(pattern,fail_once)
        page.locator('#refresh-run').click()
        expect(page.locator('#send')).to_be_enabled()
        expect(page.locator('#composer')).to_have_value(f.texts['first'])
        assert len(f.received)==0
        report.update(exit_code=0,checks=['visible_retry_before_first_task','single_failed_read','manual_read_restores_ready_without_post'])
        browser.close()
finally:
    report['source_after']=hashes();report['source_unchanged']=report['source_before']==report['source_after']
    (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
