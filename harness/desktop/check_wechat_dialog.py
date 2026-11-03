"""Actual client bundle in isolated Chrome, synthetic WeChat API fixtures only."""
import base64
import json
import sys
import time
from pathlib import Path

sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[1]
out = root / 'desktop/checks' / (time.strftime('%Y%m%d-%H%M%S') + '-wechat-dialog')
out.mkdir(parents=True)
runtime = json.loads((root / '.local/runtime.json').read_text(encoding='utf-8-sig'))
report = {'status': 'running', 'scope': 'Isolated browser, actual client bundle, synthetic connection/session/QR states; no actual WeChat action', 'errors': [], 'actions': []}
fixture = 'qx-smoke-4e02792a-de51-4e60-850d-1ba9ed875e81'
sessions = [{'id': fixture, 'title': '采购合同审查'}, {'id': 'fixture-labor', 'title': '劳动争议处理'}]
state = {'sessionId': fixture, 'connected': True, 'owner': '示例微信（测试）', 'batching': {}, 'login': None}
fail_action = False

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
        context = browser.new_context(viewport={'width': 1320, 'height': 900}, locale='zh-CN')
        context.add_init_script("window.__DSH_LOCALE__={read:async()=>({languages:['zh-CN'],preference:'zh'}),onChange:()=>{}}")
        context.route('**/api/qx-account/balance*', lambda route: route.fulfill(json={'status': 'ok', 'balances': [{'currency': 'CNY', 'total_balance': '123.45'}]}))
        context.route('**/qx-wechat/state', lambda route: route.fulfill(json=state))
        context.route('**/qx-wechat/settings', lambda route: route.fulfill(json={'csrf': 'synthetic-csrf', 'sessions': sessions}))
        def action(route):
            body = route.request.post_data_json
            report['actions'].append(body['action'])
            assert route.request.headers.get('x-qx-token') == 'synthetic-csrf'
            if fail_action:
                route.fulfill(status=400, json={'error': '测试：会话暂不可用，请重试。'})
                return
            if body['action'] == 'session':
                state['sessionId'] = body['sessionId']
            elif body['action'] == 'new-session':
                state['sessionId'] = 'fixture-new'
                sessions.append({'id': 'fixture-new', 'title': '新会话'})
            elif body['action'] in {'switch-account', 'login'}:
                # Deliberately non-scannable illustration: never a real login QR.
                svg = '<svg xmlns="http://www.w3.org/2000/svg" width="208" height="208"><rect width="208" height="208" fill="white"/><rect x="16" y="16" width="176" height="176" fill="#edf1f6"/><text x="104" y="108" text-anchor="middle" font-size="16">QR TEST ONLY</text></svg>'
                state.update(connected=False, login={'status': 'wait', 'qrImage': 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()})
            elif body['action'] == 'cancel':
                state['login'] = {'status': 'cancelled'}
            elif body['action'] == 'resume':
                state['connected'] = True
            elif body['action'] == 'pause':
                state['connected'] = False
            elif body['action'] == 'verify':
                state.update(connected=True, owner='新微信（测试）', login={'status': 'confirmed'})
            route.fulfill(json={'ok': True, 'sessionId': state['sessionId']})
        context.route('**/qx-wechat/action', action)
        page = context.new_page()
        page.on('pageerror', lambda error: report['errors'].append(str(error)))
        page.goto(runtime['url'], wait_until='domcontentloaded')
        try:
            page.get_by_role('dialog', name='预览版说明').get_by_role('button', name='继续', exact=True).click(timeout=5000)
        except Exception:
            pass
        entry = page.get_by_role('button', name='微信连接', exact=True)
        expect(entry).to_be_visible(timeout=40000)
        initial_url = page.url
        assert entry.bounding_box()['y'] < page.locator('[data-qx-balance]').bounding_box()['y']
        entry.focus()
        entry.press('Enter')
        dialog = page.get_by_role('dialog', name='微信连接', exact=True)
        expect(dialog).to_be_visible()
        expect(dialog.get_by_text('微信已连接', exact=True)).to_be_visible()
        assert len(context.pages) == 1 and page.url == initial_url
        select = dialog.get_by_label('微信使用的会话')
        expect(select).to_have_value(fixture)
        expect(select.locator('option')).to_have_text(['采购合同审查', '劳动争议处理'])
        dialog.screenshot(path=str(out / 'connected-dialog.png'))
        select.select_option(label='劳动争议处理')
        dialog.get_by_role('button', name='切换会话', exact=True).click()
        expect(dialog.get_by_text('当前：劳动争议处理', exact=True)).to_be_visible()
        dialog.get_by_role('button', name='新建会话', exact=True).click()
        expect(select).to_have_value('fixture-new')
        expect(dialog.get_by_text('当前：新会话', exact=True)).to_be_visible()
        dialog.get_by_role('button', name='重新扫码切换微信', exact=True).click()
        expect(dialog.get_by_role('img', name='微信连接二维码')).to_be_visible()
        expect(select).to_be_disabled()
        dialog.screenshot(path=str(out / 'scan-dialog.png'))
        dialog.get_by_role('button', name='取消扫码', exact=True).click()
        dialog.get_by_role('button', name='恢复原微信连接', exact=True).click()
        expect(dialog.get_by_text('微信已连接', exact=True)).to_be_visible()
        dialog.get_by_role('button', name='重新扫码切换微信', exact=True).click()
        state['login']['verifyCodeNeeded'] = True
        expect(dialog.get_by_label('手机验证码')).to_be_visible(timeout=8000)
        dialog.get_by_label('手机验证码').fill('123456')
        dialog.get_by_role('button', name='提交验证码', exact=True).click()
        expect(dialog.get_by_text('当前微信：新微信（测试）')).to_be_visible()
        fail_action = True
        select.select_option(label='采购合同审查')
        dialog.get_by_role('button', name='切换会话', exact=True).click()
        expect(dialog.get_by_role('alert')).to_contain_text('会话暂不可用')
        fail_action = False
        # Repeated Tab stays within the native modal.
        for _ in range(12):
            page.keyboard.press('Tab')
            assert page.evaluate("document.activeElement === document.body || document.querySelector('.qx-wx').contains(document.activeElement)")
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
        expect(entry).to_be_focused()
        page.evaluate("window.__qxOpenWechatRequested=true;window.dispatchEvent(new Event('qx-open-wechat'))")
        expect(dialog).to_be_visible()
        dialog.get_by_role('button', name='关闭微信连接', exact=True).click()
        expect(dialog).to_have_count(0)
        page.get_by_role('button', name='收起侧边栏', exact=True).click()
        expect(entry).to_be_visible()
        entry.click()
        expect(dialog).to_be_visible()
        page.set_viewport_size({'width': 420, 'height': 740})
        expect(dialog.get_by_role('button', name='关闭微信连接', exact=True)).to_be_in_viewport()
        assert dialog.evaluate('(element)=>element.scrollWidth <= element.clientWidth')
        dialog.screenshot(path=str(out / 'compact-dialog.png'))
        assert not report['errors'], report['errors']
        assert len(context.pages) == 1
        report.update(status='passed', checks=['原页面内弹窗，无新网页', '会话名称下拉与新建绑定', '重新扫码、取消、恢复与验证码', '错误可见且原绑定保留', '键盘焦点约束及关闭返回', '侧栏收起与窄屏可用'])
        browser.close()
except Exception as error:
    report.update(status='failed', error=str(error))
    raise
finally:
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(out / 'report.json')}, ensure_ascii=False))
