"""Synthetic localhost Chromium probe; no real desktop data or external access."""
from pathlib import Path
import os
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'tests/integration'))
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(REPO/'.local/scrapling/browsers')

import httpx
from playwright.sync_api import sync_playwright, expect
from test_assistant_routes import native, sign_in, serve
from test_assistant_profile_routes import command, commit


def test_saved_summary_and_manual_history_labels(native):
    app, _ = native
    with serve(app) as origin, httpx.Client(base_url=origin, trust_env=False) as client:
        headers = sign_in(client)
        url, value = command(client, headers)
        receipt = commit(client, headers, url, value)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':cookie.name,'value':cookie.value,'url':origin,
                                 'httpOnly':cookie.name=='qx_session'} for cookie in client.cookies.jar])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin+'/intakes/'+receipt['intake_id'])
            expect(page.locator('#save-state')).to_have_text('第 1 版已保存')
            expect(page.locator('#consultation-label')).to_have_text('接待摘要')
            expect(page.locator('#source-label')).to_have_text('接待摘要')
            expect(page.locator('#source-description a')).to_have_attribute('href','/assistant/'+receipt['conversation_id'])
            expect(page.locator('#source-description')).to_contain_text('不作为客户逐字原话')
            page.locator('#intake-form input[name=title]').fill('合成仅改标题版本二')
            page.locator('#save-intake').click()
            expect(page.locator('#save-state')).to_have_text('第 2 版已保存')
            expect(page.locator('#consultation-label')).to_have_text('接待摘要')
            expect(page.locator('#source-description a')).to_have_count(1)
            page.locator('textarea[name=consultation]').fill('合成律师人工登记版本二')
            page.locator('#save-intake').click()
            expect(page.locator('#save-state')).to_have_text('第 3 版已保存')
            expect(page.locator('#consultation-label')).to_have_text('咨询原话')
            expect(page.locator('#source-label')).to_have_text('咨询原话')
            expect(page.locator('#source-description a')).to_have_count(0)
            page.locator('#history-revision').fill('1')
            page.locator('#history-form button').click()
            expect(page.locator('#source-label')).to_have_text('接待摘要')
            expect(page.locator('#source-text')).to_have_text('合成接待摘要，客户称尚未收款，待核验。')
            expect(page.locator('#consultation-label')).to_have_text('咨询原话')
            expect(page.locator('#source-description a')).to_have_attribute('href','/assistant/'+receipt['conversation_id'])
            page.screenshot(path=str(Path(__file__).parent/'intake-history.png'), full_page=True)
            page.locator('#history-revision').fill('3')
            page.locator('#history-form button').click()
            expect(page.locator('#source-label')).to_have_text('咨询原话')
            expect(page.locator('#source-description a')).to_have_count(0)
            assert errors == []
            context.close()
            browser.close()
