"""Real React + independent headless Chrome; synthetic HTTP data only, never port 3080."""
import json
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(tempfile.mkdtemp(prefix='qx-memory-ui-'))
VENDOR = ROOT / '.local/knowledge-ui-check/vendor'
A, B = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
MID, NID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
state = {'enabled': True, 'case_enabled': True, 'stale': False, 'deleted': False, 'revision': 1,
         'content': '合成甲案记忆 <img src=x onerror=alert(1)>', 'pending_cleanup': 0, 'engine': 'not-installed'}
calls, errors = [], []
held_lists = []

HARNESS = '''
const root=ReactDOM.createRoot(document.getElementById('root'));
window.__ModuleLoader__={load({factory}){factory(name=>React).apply({
 effect(fn){fn();},reflect:{provide(){return()=>{};}},sidebarRight:{openResource(){}},
 slots:{inject(name,fn){fn();},register(o,C){if(o.name==='sidebar.footer.action')root.render(React.createElement(C,{wide:true}));}},
 sessions:{list:{getSnapshot:()=>({byId:{fixture:{id:'fixture',retainedBy:{mainView:1}}}}),subscribe:()=>()=>{}}},
 uiWorkspace:{openSession(){}}
});}};
'''
HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>案件记忆隔离验证</title>
<style>body{font-family:system-ui;margin:24px;background:#eff2f5}#root{width:260px;background:white;padding:16px}</style>
<div id="root"></div><script src="/react.js"></script><script src="/react-dom.js"></script>
<script src="/harness.js"></script><script src="/client.js"></script></html>'''
assets = {'/': ('text/html', HTML.encode()), '/harness.js': ('text/javascript', HARNESS.encode()),
          '/client.js': ('text/javascript', (ROOT/'desktop/integration/client.js').read_bytes()),
          '/react.js': ('text/javascript', (VENDOR/'react-18.3.1.development.js').read_bytes()),
          '/react-dom.js': ('text/javascript', (VENDOR/'react-dom-18.3.1.development.js').read_bytes())}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        kind, data = assets.get(self.path, ('text/plain', b''))
        self.send_response(200 if self.path in assets else 404)
        self.send_header('Content-Type', kind+'; charset=utf-8')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def status(case_id=None):
    case_enabled = False if case_id == B else state['case_enabled']
    return {'case_id': case_id, 'enabled': state['enabled'] and case_enabled,
            'global_enabled': state['enabled'], 'case_enabled': case_enabled, 'service_configured': True,
            'sync_state': 'error' if state['enabled'] and case_enabled else 'disabled',
            'pending_cleanup': 0 if case_id == B else state['pending_cleanup'],
            'revision': state['revision'], 'last_error': '增强服务暂不可用，本机记录已保留。'}


def memory():
    return {'id': MID, 'case_id': A, 'content': state['content'], 'revision': state['revision'],
            'source': {'label': '合成用户记录', 'snapshot': '合成来源原文，不随记忆修改', 'kind': 'fact'},
            'source_note_id': NID, 'updated_at': '2026-11-04T00:00:00Z',
            'source_stale': state['stale'], 'source_warning': '来源记录已被更正。' if state['stale'] else ''}


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'

    def api(route):
        request = route.request
        url = urlsplit(request.url)
        assert f'{url.scheme}://{url.netloc}' == origin, 'No external network is allowed'
        if url.path in assets:
            return route.continue_()
        if url.path == '/favicon.ico':
            return route.fulfill(status=204)
        if url.path == '/api/qx-privacy/client.js':
            return route.fulfill(content_type='text/javascript', body='window.qxPrivacy={dispose(){}}')
        if url.path == '/api/qx-account/balance':
            return route.fulfill(json={'status': 'unavailable', 'balances': []})
        if url.path == '/qx-wechat/state':
            return route.fulfill(json={'sessionId': 'fixture'})
        assert url.path.startswith('/api/qx-case-memory/'), url.path
        action = url.path.rsplit('/', 1)[1]
        query = parse_qs(url.query)
        args = json.loads(request.post_data or '{}')
        calls.append({'action': action, 'query': query, 'args': args})
        assert request.headers.get('x-qx-case-memory') == '1'
        case_id = query.get('case_id', [args.get('case_id')])[0]
        if action == 'status':
            value = status(case_id)
        elif action == 'runtime-status':
            value = {'available': True, 'phase': state['engine']}
        elif action == 'prepare':
            state['engine'] = 'installing'
            value = {'phase': 'installing'}
        elif action == 'list_cases':
            value = {'cases': [{'id': A, 'title': '合成甲案'}, {'id': B, 'title': '合成乙案'}], 'total': 2, 'next_offset': None}
        elif action == 'list':
            rows = [memory()] if case_id == A and not state['deleted'] else []
            value = {'memories': rows, 'total': len(rows), 'next_offset': None}
            if case_id == A and state.get('hold_list'):
                held_lists.append((route, value))
                return
        elif action == 'sources':
            value = {'notes': [{'id': NID, 'kind': 'fact', 'content': '合成来源原文', 'source': '合成用户记录'}], 'total': 1, 'next_offset': None}
        elif action == 'read':
            value = memory()
        elif action == 'recall':
            value = {'matches': [memory()], 'mode': 'local_fallback'}
        elif action == 'update':
            assert args['revision'] == state['revision']
            state['revision'] += 1
            state['content'] = args['content']
            value = {'memory': memory()}
        elif action == 'delete':
            assert args['revision'] == state['revision']
            state['deleted'], state['pending_cleanup'] = True, 1
            value = {'deleted': True, 'pending_cleanup': 1}
        elif action == 'add':
            assert args.get('confirmed') is True or args.get('note_id') == NID
            state['deleted'] = False
            state['content'] = args.get('content', '合成来源原文')
            value = {'memory': memory()}
        elif action == 'settings':
            state['case_enabled' if args.get('case_id') else 'enabled'] = args['enabled']
            value = status(case_id)
        else:
            raise AssertionError(action)
        route.fulfill(json=value)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 960}, service_workers='block')
            context.route('**/*', api)
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(origin)
            page.get_by_role('button', name='案件记忆', exact=True).click()
            panel = page.get_by_role('dialog', name='案件记忆')
            expect(panel).to_be_visible()
            expect(panel.get_by_label('启用案件记忆（全局）')).to_be_checked()
            assert not any(c['action'] == 'prepare' for c in calls)
            assert not any(c['action'] == 'list' for c in calls)
            panel.get_by_role('button', name='一键准备增强记忆').click()
            expect(panel.get_by_role('button', name='正在准备…')).to_be_disabled()
            panel.get_by_label('当前案件', exact=True).select_option(A)
            expect(panel.get_by_role('article')).to_have_count(1)
            assert panel.locator('img').count() == 0
            state['stale'] = True
            panel.get_by_text('查看保存时的来源原文', exact=True).click()
            expect(panel.get_by_text('请重新选择本案当前记录；修订记忆不会更新来源。', exact=False)).to_be_visible()
            expect(panel.get_by_text('合成来源原文，不随记忆修改', exact=True)).to_be_visible()
            panel.get_by_role('button', name='修订记忆', exact=True).click()
            panel.get_by_label('修订后的记忆正文').fill('已修订的合成记忆')
            panel.get_by_role('button', name='保存修订', exact=True).click()
            expect(panel.get_by_role('article').get_by_text('已修订的合成记忆', exact=True)).to_be_visible()
            panel.get_by_label('检索本案记忆').fill('修订')
            panel.get_by_role('button', name='检索记忆', exact=True).click()
            expect(panel.get_by_text('当前使用本机关键词匹配', exact=False)).to_be_visible()
            panel.get_by_role('button', name='删除记忆', exact=True).click()
            assert not any(c['action'] == 'delete' for c in calls)
            expect(panel.get_by_role('button', name='取消删除')).to_be_focused()
            panel.get_by_role('button', name='确认删除此记忆').click()
            expect(panel.get_by_text('有 1 份旧增强索引待清理。', exact=False)).to_be_visible()
            expect(panel.get_by_text('本案还没有记忆。', exact=False)).to_be_visible()
            panel.get_by_role('button', name='添加记忆', exact=True).click()
            panel.get_by_label('记忆来源', exact=True).select_option('manual')
            panel.get_by_label('来源说明', exact=True).fill('合成电话确认')
            panel.get_by_label('记忆正文', exact=True).fill('合成手工记忆')
            expect(panel.get_by_role('button', name='保存到本案记忆')).to_be_disabled()
            panel.get_by_label('我已核对上述内容和来源').check()
            panel.get_by_role('button', name='保存到本案记忆').click()
            expect(panel.get_by_role('article')).to_have_count(1)
            expect(panel.get_by_role('article').get_by_text('合成手工记忆', exact=True)).to_be_visible()
            panel.get_by_role('button', name='添加记忆', exact=True).click()
            panel.get_by_label('记忆来源', exact=True).select_option('note')
            expect(panel.get_by_role('button', name='保存到本案记忆')).to_be_disabled()
            panel.get_by_label('选择一条记录', exact=True).select_option(NID)
            expect(panel.get_by_text('合成来源原文', exact=True)).to_be_visible()
            panel.get_by_role('button', name='保存到本案记忆').click()
            expect(panel.get_by_role('article').get_by_text('合成来源原文', exact=True)).to_be_visible()
            selected_args = [c['args'] for c in calls if c['action'] == 'add'][-1]
            assert selected_args == {'case_id': A, 'note_id': NID}
            panel.get_by_label('启用案件记忆（全局）').click()
            expect(panel.get_by_label('启用案件记忆（全局）')).not_to_be_checked()
            expect(panel.get_by_role('button', name='添加记忆', exact=True)).to_be_disabled()
            panel.get_by_label('启用案件记忆（全局）').click()
            expect(panel.get_by_label('启用案件记忆（全局）')).to_be_checked()
            expect(panel.get_by_role('button', name='添加记忆', exact=True)).to_be_enabled()
            panel.locator('.qx-memory-body').evaluate('(e)=>e.scrollTop=0')
            page.screenshot(path=str(OUT/'desktop.png'), full_page=True)
            panel.get_by_role('article').scroll_into_view_if_needed()
            page.screenshot(path=str(OUT/'desktop-content.png'), full_page=True)
            state['hold_list'] = True
            panel.get_by_role('button', name='添加记忆', exact=True).click()
            panel.get_by_label('选择一条记录', exact=True).select_option(NID)
            panel.get_by_role('button', name='保存到本案记忆').click()
            for _ in range(40):
                if held_lists:
                    break
                page.wait_for_timeout(50)
            assert held_lists, 'A mutation refresh is held in flight'
            panel.get_by_label('当前案件', exact=True).select_option(B)
            expect(panel.get_by_text('本案还没有记忆。', exact=False)).to_be_visible()
            expect(panel.get_by_role('article')).to_have_count(0)
            expect(panel.get_by_label('本案使用记忆', exact=True)).not_to_be_checked()
            late_boundary = len(calls)
            state['hold_list'] = False
            for pending, value in held_lists:
                pending.fulfill(json=value)
            page.wait_for_timeout(300)
            assert not [c for c in calls[late_boundary:] if c['action'] == 'status' and c['query'].get('case_id') == [A]], 'Late A refresh must not restart status requests after selecting B'
            expect(panel.get_by_label('本案使用记忆', exact=True)).not_to_be_checked()
            expect(panel.get_by_text('有 1 份旧增强索引待清理。', exact=False)).to_have_count(0)
            page.set_viewport_size({'width': 390, 'height': 844})
            panel.locator('.qx-memory-body').evaluate('(e)=>e.scrollTop=0')
            page.screenshot(path=str(OUT/'mobile.png'), full_page=True)
            panel.get_by_text('本案还没有记忆。', exact=False).scroll_into_view_if_needed()
            page.screenshot(path=str(OUT/'mobile-content.png'), full_page=True)
            assert panel.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
            assert panel.locator('.qx-memory-body').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
            page.keyboard.press('Escape')
            expect(panel).not_to_be_visible()
            expect(page.get_by_role('button', name='案件记忆', exact=True)).to_be_focused()
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({'status':'passed','scope':'synthetic isolated React and Chrome','screenshots':str(OUT),
                      'checks':['default-on','explicit-prepare','case-selection','source-live-refresh','revision','local-fallback',
                                'delete-confirmation','pending-cleanup','manual-confirmation','selected-note','global-toggle',
                                'case-isolation','delayed-cross-case-response','mobile','focus-return'],
                      'page_errors':errors}, ensure_ascii=False))


if __name__ == '__main__':
    main()
