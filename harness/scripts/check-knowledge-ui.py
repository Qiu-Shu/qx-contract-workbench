"""Isolated real-React browser check. No live workbench, accounts, files or model calls.

Run with the Playwright-enabled Python environment. The two pinned test-only React
UMD assets are cached under .local; npm tarball integrity is checked before use.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '.local' / 'knowledge-ui-check'
OUT = BASE / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
OUT.mkdir(parents=True)
REPORT = {'status': 'running', 'scope': 'isolated mock Harness + real React + independent headless Chrome',
          'checks': [], 'console_errors': [], 'page_errors': [], 'blocked_requests': [], 'api_requests': []}


def react_asset(package):
    version = '18.3.1'
    target = BASE / 'vendor' / f'{package}-{version}.development.js'
    if not target.exists():
        metadata = json.load(urllib.request.urlopen(f'https://registry.npmjs.org/{package}/{version}', timeout=30))
        dist = metadata['dist']
        if urlsplit(dist['tarball']).netloc != 'registry.npmjs.org':
            raise RuntimeError('Unexpected registry tarball host')
        archive = urllib.request.urlopen(dist['tarball'], timeout=60).read()
        algorithm, expected = dist['integrity'].split('-', 1)
        if algorithm != 'sha512' or base64.b64encode(hashlib.sha512(archive).digest()).decode() != expected:
            raise RuntimeError('React fixture tarball integrity mismatch')
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
            value = bundle.extractfile(f'package/umd/{package}.development.js').read()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    return target.read_bytes()


HARNESS = r"""
const root=ReactDOM.createRoot(document.getElementById('root'));
window.__fixture={registered:[],effects:[]};
window.__ModuleLoader__={load({id,factory}){
  window.__fixture.moduleId=id;
  const plugin=factory(name=>{if(name==='react')return React;throw Error('Unexpected module '+name)});
  if(typeof plugin.apply!=='function')throw Error('Client registration did not expose apply');
  window.__fixture.inject=plugin.inject;
  const ctx={
    reflect:{provide:()=>()=>{}},
    sidebarRight:{openResource:()=>{}},
    effect(fn){window.__fixture.effects.push(fn());},
    slots:{inject(name,fn){return fn();},register(options,Component){
      window.__fixture.registered.push(options.name);
      if(options.name==='sidebar.footer.action')root.render(React.createElement(Component,{wide:true}));
    }},
    sessions:{list:{getSnapshot:()=>({byId:{fixture:{id:'fixture-session',retainedBy:{mainView:1}}}}),subscribe:()=>()=>{}}},
    uiWorkspace:{openSession(id){window.__fixture.selectedSession=id}}
  };
  plugin.apply(ctx);
}};
"""
HTML = b'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Isolated knowledge check</title>
<style>body{font-family:system-ui;margin:24px;background:#eff2f5}#root{width:260px;background:white;padding:16px}</style>
<div id="root"></div><script src="/react.js"></script><script src="/react-dom.js"></script>
<script src="/harness.js"></script><script src="/client.js"></script></html>'''


def main():
    client = (ROOT / 'desktop/integration/client.js').read_bytes()
    (OUT / 'client-under-test.js').write_bytes(client)
    REPORT['client_sha256'] = hashlib.sha256(client).hexdigest()
    assets = {'/': ('text/html', HTML), '/react.js': ('text/javascript', react_asset('react')),
              '/react-dom.js': ('text/javascript', react_asset('react-dom')),
              '/api/qx-business/client.js': ('text/javascript', b'window.qxInstallBusiness=()=>()=>{};'),
              '/api/qx-layered/client.js': ('text/javascript', (ROOT / 'desktop/integration/knowledge-client.js').read_bytes()),
              '/harness.js': ('text/javascript', HARNESS.encode()), '/client.js': ('text/javascript', client)}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            content_type, body = assets.get(self.path, ('text/plain', b'Not found'))
            self.send_response(200 if self.path in assets else 404)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    REPORT['origin'] = origin
    scenario = {'mode': 'normal', 'phase': 'normal', 'archived': False}
    doc = {'id': 'synthetic-document', 'title': '虚构合同范本 <img src=x onerror=alert(1)>', 'state': 'ready',
           'category': '合成资料', 'created_at': '2026-11-03T00:00:00Z', 'busy': False, 'warnings': []}

    def api(route):
        request = route.request
        url = urlsplit(request.url)
        if f'{url.scheme}://{url.netloc}' != origin:
            REPORT['blocked_requests'].append(request.url)
            route.abort()
            return
        if url.path in assets or url.path == '/favicon.ico':
            if url.path == '/favicon.ico':
                route.fulfill(status=204)
            else:
                route.continue_()
            return
        REPORT['api_requests'].append({'path': url.path, 'method': request.method, 'query': url.query})
        query = parse_qs(url.query)
        value = {}
        if url.path == '/api/qx-privacy/client.js':
            route.fulfill(content_type='text/javascript', body='window.qxPrivacy={dispose(){}};')
            return
        if url.path == '/qx-wechat/state':
            value = {'sessionId': 'fixture-session', 'connected': False}
        elif url.path == '/api/qx-account/balance':
            value = {'status': 'unavailable', 'balances': []}
        elif url.path == '/api/qx-knowledge/documents':
            if scenario['mode'] == 'http-error':
                route.fulfill(status=503, json={'error': '合成服务错误：请稍后重试'})
                return
            if scenario['mode'] == 'malformed':
                value = {'documents': None, 'total': 1, 'next_offset': None}
            else:
                value = {'documents': [doc], 'total': 1, 'next_offset': None}
        elif url.path == '/api/qx-knowledge/search':
            value = {'matches': [{'title': doc['title'], 'category': doc['category'], 'excerpt': '跨段合成原文',
                                  'location': '第 1–2 段', 'citation': 'KB:fixture:1',
                                  'citations': [{'citation': 'KB:fixture:1'}, {'citation': 'KB:fixture:2'}]}], 'has_more': False}
        elif url.path == '/api/qx-knowledge/citation':
            citation = query['reference'][0]
            value = {'document_id': doc['id'], 'title': doc['title'], 'citation': citation,
                     'text': '合成第二段原文' if citation.endswith(':2') else '合成第一段原文', 'location': '合成段落'}
        elif url.path == '/api/qx-knowledge/read':
            value = {'document_id': doc['id'], 'title': doc['title'], 'next_start': None,
                     'chunks': [{'text': '合成完整原文', 'location': '第 1 段', 'citation': 'KB:fixture:1'}]}
        elif url.path == '/api/qx-knowledge/backup':
            assert request.method == 'POST'
            value = {'documents': 1, 'download': '/api/qx-knowledge/backup-download?token=synthetic-only'}
        elif url.path == '/api/qx-knowledge/restore':
            assert request.method == 'POST'
            assert request.headers['content-type'] == 'application/zip'
            assert request.post_data_buffer == b'not-a-real-archive-test-only'
            value = {'imported': 1, 'skipped': 0}
        elif url.path == '/api/qx-knowledge/archive':
            value = {'archived': True}
        else:
            REPORT['blocked_requests'].append(request.url)
            route.abort()
            return
        if url.path.startswith('/api/qx-knowledge/'):
            assert request.headers.get('x-qx-knowledge') == '1'
        route.fulfill(json=value)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 900}, service_workers='block')
            context.route('**/*', api)
            page = context.new_page()
            page.on('console', lambda message: REPORT['console_errors'].append({'phase': scenario['phase'], 'text': message.text}) if message.type == 'error' else None)
            page.on('pageerror', lambda error: REPORT['page_errors'].append({'phase': scenario['phase'], 'text': str(error)}))
            page.goto(origin, wait_until='networkidle')
            assert page.evaluate('window.__fixture.moduleId') == '@qunxing/desktop-session'
            assert 'sidebar.footer.action' in page.evaluate('window.__fixture.registered')
            page.get_by_role('button', name='律所知识库', exact=True).click()
            panel = page.get_by_role('dialog', name='律所知识库')
            expect(panel).to_be_visible()
            expect(panel.get_by_role('cell', name=doc['title'], exact=False)).to_be_visible()
            assert panel.locator('img').count() == 0
            page.screenshot(path=str(OUT / '01-list.png'), full_page=True)
            REPORT['checks'].append('ModuleLoader registration, sidebar click, real React modal, populated list, title escaping')
            page.get_by_role('button', name='查看原文', exact=True).click()
            expect(page.get_by_text('合成完整原文', exact=True)).to_be_visible()
            page.get_by_role('button', name='收起原文', exact=True).click()
            page.get_by_role('searchbox', name='检索知识库关键词').fill('跨段 合成')
            page.get_by_role('button', name='检索', exact=True).click()
            page.get_by_role('button', name='定位第 2 段原文', exact=True).click()
            expect(page.get_by_text('合成第二段原文', exact=True)).to_be_visible()
            REPORT['checks'].append('Read source; cross-chunk search exposes two independent citation buttons; second citation opens correct text')
            page.get_by_role('button', name='备份知识库', exact=True).click()
            expect(page.get_by_role('link', name='下载备份')).to_have_attribute('href', '/api/qx-knowledge/backup-download?token=synthetic-only')
            page.locator('input[type=file][accept=".zip"]').set_input_files({'name': 'synthetic.zip', 'mimeType': 'application/zip', 'buffer': b'not-a-real-archive-test-only'})
            expect(page.get_by_role('status')).to_contain_text('已恢复 1 份资料')
            REPORT['checks'].append('Backup POST and download link; restore file POST, content type and restored-count notice')
            page.get_by_role('button', name='关闭知识库', exact=True).click()
            expect(panel).to_have_count(0)
            REPORT['checks'].append('Close button removes modal')

            scenario.update(mode='http-error', phase='expected-http-error')
            page.get_by_role('button', name='律所知识库', exact=True).click()
            expect(page.get_by_role('alert')).to_contain_text('合成服务错误')
            page.screenshot(path=str(OUT / '02-service-error.png'), full_page=True)
            scenario.update(mode='normal', phase='normal')
            expect(panel.get_by_role('cell', name=doc['title'], exact=False)).to_be_visible(timeout=7000)
            expect(page.get_by_role('alert')).to_have_count(0)
            REPORT['checks'].append('Background list refresh clears its stale error after the service recovers')
            page.get_by_role('button', name='关闭知识库', exact=True).click()
            scenario.update(mode='normal', phase='normal')
            page.get_by_role('button', name='律所知识库', exact=True).click()
            expect(panel.get_by_role('cell', name=doc['title'], exact=False)).to_be_visible()
            expect(page.get_by_role('alert')).to_have_count(0)
            page.keyboard.press('Escape')
            expect(panel).to_have_count(0)
            REPORT['checks'].append('API failure shows readable error; close/reopen retries successfully; Escape closes modal')

            scenario.update(mode='malformed', phase='intentional-render-failure')
            page.get_by_role('button', name='律所知识库', exact=True).click()
            expect(page.get_by_text('知识库界面未能显示。', exact=True)).to_be_visible()
            page.get_by_text('查看错误信息', exact=True).click()
            expect(page.locator('details pre')).not_to_be_empty()
            page.screenshot(path=str(OUT / '03-boundary-error.png'), full_page=True)
            scenario.update(mode='normal', phase='normal')
            page.get_by_role('button', name='重试', exact=True).click()
            expect(panel.get_by_role('cell', name=doc['title'], exact=False)).to_be_visible()
            page.screenshot(path=str(OUT / '04-retry-recovered.png'), full_page=True)
            page.keyboard.press('Escape')
            scenario.update(mode='malformed', phase='intentional-render-failure')
            page.get_by_role('button', name='律所知识库', exact=True).click()
            page.get_by_role('button', name='关闭', exact=True).click()
            expect(page.get_by_role('alert')).to_have_count(0)
            REPORT['checks'].append('ErrorBoundary displays details; retry remounts successfully; boundary close returns to sidebar')
            scenario.update(mode='normal', phase='normal')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.get_by_role('button', name='律所知识库', exact=True).click()
            expect(panel.get_by_role('cell', name=doc['title'], exact=False)).to_be_visible()
            box = panel.bounding_box()
            assert box['width'] <= 390 and box['x'] >= 0
            page.screenshot(path=str(OUT / '05-narrow.png'), full_page=True)
            REPORT['checks'].append('390px viewport keeps dialog within screen')
            assert not REPORT['blocked_requests'], REPORT['blocked_requests']
            assert not [error for error in REPORT['page_errors'] if error['phase'] != 'intentional-render-failure'], REPORT['page_errors']
            assert not [error for error in REPORT['console_errors'] if error['phase'] not in ('intentional-render-failure', 'expected-http-error')], REPORT['console_errors']
            REPORT['status'] = 'passed'
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        REPORT['status'] = 'failed'
        REPORT['error'] = str(error)
        raise
    finally:
        REPORT['artifacts'] = str(OUT)
        (OUT / 'result.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': REPORT['status'], 'checks': len(REPORT['checks']), 'artifacts': str(OUT)}, ensure_ascii=False))
