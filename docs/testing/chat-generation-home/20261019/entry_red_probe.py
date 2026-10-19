"""Real browser RED for the missing homepage generation entry wiring."""
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect
from ui_fixture import ui_fixture

base=Path(__file__).resolve().parent
root=base.parents[1]
with ui_fixture(base/('entry-red-'+uuid4().hex[:8])) as fixture:
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path=str(root/'.local/scrapling/browsers/chromium-1243/chrome-win64/chrome.exe'),headless=True)
        page=browser.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            page.goto(fixture.origin+'/login')
            page.get_by_label('用户名').fill(fixture.credentials['username'])
            page.get_by_label('密码').fill(fixture.credentials['password'])
            page.get_by_role('button',name='登录',exact=True).click()
            page.wait_for_url(fixture.origin+'/assistant')
            page.locator('#composer').fill(fixture.texts['first'])
            expect(page.locator('#save-status')).to_have_text('草稿已保存到本机')
            expect(page.locator('#send')).to_be_enabled(timeout=5000)
        finally:
            print('PAGE_ERRORS',errors)
            browser.close()
