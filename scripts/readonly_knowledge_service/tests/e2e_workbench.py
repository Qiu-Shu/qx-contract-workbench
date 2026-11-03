#!/usr/bin/env python3
"""贯通级验证：真实工作台进程 + 真实知识服务进程，全部走 HTTP。

不做任何 import 打桩：登录、CSRF、检索、原文回读都是真的网络请求。
用法：
    python3 e2e_workbench.py --base http://127.0.0.1:8791 --out evidence/e2e_workbench.json
退出码 0 表示全部断言成立。
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RESULTS: list[dict] = []


def record(name: str, ok: bool, detail, elapsed_ms: float = 0.0) -> None:
    RESULTS.append({'step': name, 'ok': bool(ok), 'elapsed_ms': round(elapsed_ms, 2), 'detail': detail})
    print(('PASS  ' if ok else 'FAIL  ') + f'{name}  ({elapsed_ms:.0f} ms)')


class Session:
    def __init__(self, base: str):
        self.base = base.rstrip('/')
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ''
        self.cookies: dict[str, str] = {}

    def _cookie_header(self) -> str:
        return '; '.join(f'{c.name}={c.value}' for c in self.jar)

    def call(self, method: str, path: str, payload=None, *, headers=None, cookie_override=None):
        url = self.base + path
        data = None
        final_headers = {'Origin': self.base, 'Accept': 'application/json'}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            final_headers['Content-Type'] = 'application/json'
        cookie = cookie_override if cookie_override is not None else self._cookie_header()
        if cookie:
            final_headers['Cookie'] = cookie
        if headers:
            final_headers.update(headers)
        request = urllib.request.Request(url, data=data, method=method, headers=final_headers)
        started = time.perf_counter()
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read()
                status = response.status
                ctype = response.headers.get('content-type', '')
        except urllib.error.HTTPError as error:
            raw = error.read()
            status = error.code
            ctype = error.headers.get('content-type', '')
        elapsed = (time.perf_counter() - started) * 1000
        if 'json' in ctype:
            try:
                body = json.loads(raw.decode('utf-8'))
            except ValueError:
                body = {'_raw': raw.decode('utf-8', 'replace')[:400]}
        else:
            body = {'_text': raw.decode('utf-8', 'replace')}
        return status, body, elapsed

    def login(self, username: str, password: str):
        status, body, elapsed = self.call('POST', '/api/login', {'username': username, 'password': password})
        if status == 200 and 'csrf_token' in body:
            self.csrf = body['csrf_token']
            self.cookies = {c.name: c.value for c in self.jar}
        return status, body, elapsed


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8791')
    parser.add_argument('--user', default='pilot')
    parser.add_argument('--password', default='pilot123')
    parser.add_argument('--out', default='')
    args = parser.parse_args()

    session = Session(args.base)
    worst = 0.0

    # 1. 未登录：API 必须拒绝，不能"因为本地进程就放行"
    status, body, ms = session.call('GET', '/api/knowledge/status')
    record('未登录访问 status 被拒', status == 401, {'http': status, 'code': body.get('code')}, ms)

    # 2. 合成登录
    status, body, ms = session.login(args.user, args.password)
    ok = status == 200 and len(session.csrf) >= 16 and 'qx_session' in session.cookies and 'qx_csrf' in session.cookies
    record('合成登录取得会话与 CSRF', ok, {
        'http': status,
        'csrf_len': len(session.csrf),
        'cookies': sorted(session.cookies),
    }, ms)

    # 3. 页面入口在已登录时可达，且不泄漏服务地址/凭据
    status, body, ms = session.call('GET', '/knowledge', headers={'Accept': 'text/html'})
    text = body.get('_text', '')
    leaked = ('127.0.0.1:60058' in text) or ('X-KB-Token' in text) or ('KB_SERVICE_TOKEN' in text)
    record('知识服务页面可达且不泄漏后端地址', status == 200 and '知识服务' in text and not leaked,
           {'http': status, 'contains_marker': '知识服务' in text, 'leaked_backend': leaked}, ms)

    # 4. 状态透传：真实 KB 计数
    status, body, ms = session.call('GET', '/api/knowledge/status')
    assets = (body or {}).get('assets') or {}
    law = assets.get('law') or {}
    cases = assets.get('cases') or {}
    readonly = ((body or {}).get('readonly') or {}).get('legal_db') or {}
    ok = (status == 200 and law.get('units', 0) > 0 and cases.get('cases', 0) > 0
          and readonly.get('write_attempt_blocked') is True and readonly.get('mode') == 'ro')
    record('status 返回真实 KB 计数且只读自证成立', ok,
           {'http': status, 'law': law, 'cases': cases, 'readonly': readonly,
            'rankers': (body or {}).get('rankers')}, ms)

    # 5. 检索：一条法条 + 一条案例
    query = '违约金过高 适当减少'
    status, page, ms = session.call('POST', '/api/knowledge/search',
                                    {'query': query, 'kinds': ['law', 'case'], 'limit': 5},
                                    headers={'X-CSRF-Token': session.csrf})
    groups = (page or {}).get('groups') or {}
    laws = groups.get('law') or []
    cases_hit = groups.get('case') or []
    ok = status == 200 and page.get('state') == 'ready' and len(laws) >= 1 and len(cases_hit) >= 1
    record('检索同时命中法条与案例', ok, {
        'http': status, 'state': page.get('state'), 'law_hits': len(laws), 'case_hits': len(cases_hit),
        'elapsed_ms_service': page.get('elapsed_ms'), 'degraded': page.get('degraded'),
    }, ms)

    # 5b. 真实库里有文档的 heading_path 是字面量 '[]'，不能原样流到界面
    placeholders = [c['source_id'] for c in laws + cases_hit if '[]' in c.get('heading_path', '')]
    record('heading_path 占位符未泄漏到界面', not placeholders, {'offenders': placeholders})

    # 6. 缺 CSRF 必须拒（写动作不能只靠 cookie）
    status, body, ms = session.call('POST', '/api/knowledge/search', {'query': '定金', 'limit': 1})
    record('缺 CSRF 的检索被拒', status in (403, 401), {'http': status, 'code': body.get('code')}, ms)

    # 7. 引用自洽 + 原文回读（法条、案例各一）
    for kind, hits in (('law', laws), ('case', cases_hit)):
        if not hits:
            record(f'{kind} 引用回读', False, '没有可回读的命中')
            continue
        citation = hits[0]
        snippet = citation['snippet']
        loc = citation['location']
        sid = citation['source_id']
        snippet_sha_ok = sha(snippet['text']) == snippet['sha256']
        inside = loc['char_start'] <= snippet['start'] < snippet['end'] <= loc['char_end']
        status, view, ms = session.call('GET', '/api/knowledge/sources/' + urllib.parse.quote(sid, safe=''))
        content = (view or {}).get('content') or {}
        contained = bool(content.get('text')) and snippet['text'] in content['text']
        base = content.get('start', 0)
        offset_ok = contained and content['text'].index(snippet['text']) + base == snippet['start']
        record(f'{kind} 引用片段在原文回读中可定位', status == 200 and snippet_sha_ok and inside and offset_ok, {
            'http': status, 'source_id': sid, 'title': citation['title'][:60],
            'snippet_sha_ok': snippet_sha_ok, 'snippet_inside_location': inside,
            'found_in_original': contained, 'absolute_offset_ok': offset_ok,
            'location': {k: loc[k] for k in ('line_start', 'line_end', 'char_start', 'char_end', 'basis')},
            'source_version': citation['source_version'],
            'readback_basis': (view or {}).get('location', {}).get('basis'),
            'truncated': content.get('truncated'),
        }, ms)
        worst = max(worst, ms)

    # 8. 越界范围必须阻断，不能截到块外
    if laws:
        sid = laws[0]['source_id']
        loc = laws[0]['location']
        forged_end = loc['char_end'] + 5000
        status, body, ms = session.call(
            'GET', '/api/knowledge/sources/' + urllib.parse.quote(sid, safe='') + f'?start=0&end={forged_end}')
        record('越界范围被拒', status == 409 and body.get('code') == 'KNOWLEDGE_RANGE_INVALID',
               {'http': status, 'code': body.get('code'), 'requested_end': forged_end,
                'block_end': loc['char_end']}, ms)

    # 9. 格式合法但不存在的来源 → 404，而不是 500 或空内容
    ghost = 'law_unit:unit_' + 'f' * 24
    status, body, ms = session.call('GET', '/api/knowledge/sources/' + urllib.parse.quote(ghost, safe=''))
    record('不存在的来源返回 404', status == 404 and body.get('code') == 'KNOWLEDGE_SOURCE_NOT_FOUND',
           {'http': status, 'code': body.get('code')}, ms)

    # 10. 恶意路径不得进入客户端
    for bad in ('../../etc/passwd', 'law_unit:../../etc/passwd', 'file:///etc/passwd'):
        status, body, ms = session.call('GET', '/api/knowledge/sources/' + urllib.parse.quote(bad, safe=''))
        record(f'恶意来源被拒 {bad[:24]}', status in (422, 404),
               {'http': status, 'code': body.get('code')}, ms)

    # 11. 非法检索词
    for bad in ('x' * 201, '\u0000定金'):
        status, body, ms = session.call('POST', '/api/knowledge/search', {'query': bad, 'limit': 3},
                                        headers={'X-CSRF-Token': session.csrf})
        record(f'非法检索词被拒 len={len(bad)}', status == 422, {'http': status, 'code': body.get('code')}, ms)

    # 12. 空命中与服务故障必须可区分
    status, page, ms = session.call('POST', '/api/knowledge/search',
                                    {'query': '量子纠缠钻石质押', 'kinds': ['law', 'case'], 'limit': 3},
                                    headers={'X-CSRF-Token': session.csrf})
    record('空结果不是错误', status == 200 and page.get('state') == 'empty',
           {'http': status, 'state': page.get('state'), 'notes': page.get('notes')}, ms)

    # 13. 跨会话：另一会话的 cookie 不能沿用旧会话的 CSRF
    other = Session(args.base)
    status, _, ms = other.login(args.user, args.password)
    stolen = session.csrf
    status, body, ms = other.call('POST', '/api/knowledge/search', {'query': '定金', 'limit': 1},
                                  headers={'X-CSRF-Token': stolen})
    record('跨会话盗用 CSRF 被拒', status == 403, {'http': status, 'code': body.get('code')}, ms)

    # 14. 撤权后：旧 cookie 立刻失效
    session.call('POST', '/api/logout', headers={'X-CSRF-Token': session.csrf})
    revoked_cookie = '; '.join(f'{k}={v}' for k, v in session.cookies.items())
    status, body, ms = session.call('GET', '/api/knowledge/status', cookie_override=revoked_cookie)
    record('登出后旧会话读来源被拒', status == 401, {'http': status, 'code': body.get('code')}, ms)

    # 汇总
    ok_all = all(item['ok'] for item in RESULTS)
    payload = {
        'base': args.base,
        'account': args.user,
        'steps': RESULTS,
        'passed': sum(1 for r in RESULTS if r['ok']),
        'total': len(RESULTS),
        'all_passed': ok_all,
        'slowest_source_read_ms': round(worst, 2),
        'note': '全部请求经真实 HTTP 到达工作台进程，工作台再经真实 HTTP 访问独立知识服务进程；未使用 MockTransport。',
    }
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    print()
    print(f"{payload['passed']}/{payload['total']} 通过；all_passed={ok_all}")
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
