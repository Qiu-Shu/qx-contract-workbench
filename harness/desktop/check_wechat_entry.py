"""Check the sidebar entry and in-app dialog in isolated Chrome; no model or WeChat actions.

Balance and connection state are explicit fixtures. The UI and /qx-wechat page
are served by the running host, without restarting it or opening the user's UI.
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[1]
out = root / 'desktop' / 'checks' / (time.strftime('%Y%m%d-%H%M%S') + '-wechat-entry')
out.mkdir(parents=True)
runtime = json.loads((root / '.local/runtime.json').read_text(encoding='utf-8-sig'))
report = {'status': 'running', 'scope': 'Isolated Chrome; actual sidebar and connection page; fixture balance/state; no model or WeChat actions', 'page_errors': [], 'wechat_actions': []}
fixture_session = 'qx-smoke-4e02792a-de51-4e60-850d-1ba9ed875e81'

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
        context = browser.new_context(viewport={'width': 1320, 'height': 900}, locale='zh-CN')
        context.add_init_script("window.__DSH_LOCALE__={read:async()=>({languages:['zh-CN'],preference:'zh'}),onChange:()=>{}}")
        context.route('**/api/qx-account/balance*', lambda route: route.fulfill(json={
            'status': 'ok', 'balances': [{'currency': 'CNY', 'total_balance': '123.45'}]}))
        context.route('**/qx-wechat/state', lambda route: route.fulfill(json={
            'sessionId': fixture_session, 'workspace': '合成验证工作区', 'connected': False}))
        context.route('**/qx-wechat/settings', lambda route: route.fulfill(json={
            'csrf': 'synthetic-only', 'sessions': [{'id': fixture_session, 'title': '虚构验收会话'}]}))
        def reject_action(route):
            report['wechat_actions'].append(route.request.method)
            route.abort()
        context.route('**/qx-wechat/action', reject_action)
        context.on('page', lambda page: page.on('pageerror', lambda error: report['page_errors'].append(str(error))))
        page = context.new_page()
        page.goto(runtime['url'], wait_until='domcontentloaded')
        try:
            page.get_by_role('dialog', name='预览版说明').get_by_role('button', name='继续', exact=True).click(timeout=8000)
        except Exception:
            pass
        link = page.get_by_role('button', name='微信连接', exact=True)
        expect(link).to_be_visible(timeout=40000)
        expect(page.locator('.qx-wordmark')).to_have_text('群兴')
        expect(page.locator('.qx-balance-values')).to_have_text('123.45 CNY')
        for label in ['插件', '自动化任务', '更多']:
            expect(page.get_by_role('button', name=label, exact=True)).to_have_count(0)
        link_box = link.bounding_box()
        balance_box = page.locator('[data-qx-balance]').bounding_box()
        assert link_box['y'] + link_box['height'] <= balance_box['y'], 'WeChat entry is not above the balance'
        assert link_box['x'] < 300 and link_box['y'] > 600, 'Entry is not in the bottom-left sidebar'
        page.locator('.qx-sidebar-account').screenshot(path=str(out / 'expanded-footer.png'))
        link.focus()
        expect(link).to_be_focused()
        before = page.url
        link.press('Enter')
        panel = page.get_by_role('dialog', name='微信连接', exact=True)
        expect(panel).to_be_visible()
        expect(panel.get_by_role('heading', name='微信连接', exact=True)).to_be_visible()
        assert page.url == before, 'Opening the entry navigated away from the conversation'
        assert len(context.pages) == 1
        report['connection_dialog'] = {'heading_visible': True, 'opened_in_app': True}
        panel.get_by_role('button', name='关闭微信连接', exact=True).click()
        page.get_by_role('button', name='收起侧边栏', exact=True).click()
        expect(page.locator('.qx-sidebar-account')).to_have_class('qx-sidebar-account qx-sidebar-account-compact')
        expect(link).to_be_visible()
        expect(link).to_be_in_viewport()
        expect(link).to_have_attribute('title', '微信连接')
        expect(page.get_by_role('button', name='刷新 DeepSeek 余额', exact=True)).to_be_visible()
        assert link.bounding_box()['y'] < page.locator('[data-qx-balance]').bounding_box()['y']
        page.locator('.qx-sidebar-account').screenshot(path=str(out / 'collapsed-footer.png'))
        assert not report['wechat_actions'], report['wechat_actions']
        assert not report['page_errors'], report['page_errors']
        report.update(status='passed', checks=['微信连接位于左下余额正上方', '键盘 Enter 打开程序内弹窗，原聊天未导航', '侧栏收起后入口及余额刷新均可达', '群兴标识及隐藏导航保持', '未请求任何微信操作接口'])
        browser.close()
except Exception as error:
    report.update(status='failed', error=str(error))
    raise
finally:
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'status': report['status'], 'report': str(out / 'report.json')}, ensure_ascii=False))
