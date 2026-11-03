#!/usr/bin/env python3
"""原聊天端到端：在真实工作台上走「检索法律资料」这条路。

这条路径过去只会在页面上显示「本机尚未连接法律资料库，未执行查询」——因为没配
本地法库时研究任务拿到的是 `LegalLibraryAdapter(None)`。这里全程走 HTTP、不做任何
import 打桩，验证：会话 → 提交检索 → 回执里是知识服务的法条/案例 → 打开保存的引用
→ 用检索时的版本回读原文。顺带验证版本不一致会被阻断。

用法：
    python3 e2e_main_chat.py --base http://127.0.0.1:8791
退出码 0 表示全部断言成立。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from e2e_workbench import Session  # noqa: E402

RESULTS: list[dict] = []


def record(name: str, ok: bool, detail, elapsed_ms: float = 0.0) -> None:
    RESULTS.append({'step': name, 'ok': bool(ok), 'elapsed_ms': round(elapsed_ms, 2), 'detail': detail})
    print(('PASS  ' if ok else 'FAIL  ') + f'{name}  ({elapsed_ms:.0f} ms)')
    if not ok:
        print('      ' + json.dumps(detail, ensure_ascii=False)[:600])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8791')
    parser.add_argument('--user', default='pilot')
    parser.add_argument('--password', default='pilot123')
    parser.add_argument('--keyword', default='违约金')
    parser.add_argument('--out', default='')
    args = parser.parse_args()

    session = Session(args.base)
    status, body, ms = session.login(args.user, args.password)
    record('登录取得会话与 CSRF', status == 200 and len(session.csrf) >= 16,
           {'http': status}, ms)
    if status != 200:
        return report(args)

    csrf = {'X-CSRF-Token': session.csrf}

    # 1. 建会话
    status, body, ms = session.call('POST', '/api/assistant/conversations',
                                    {'request_id': str(uuid.uuid4()), 'display_title': '只读试点复验'},
                                    headers=csrf)
    conversation = ((body or {}).get('scope') or {}).get('conversation_id')
    record('创建会话', status == 201 and bool(conversation), {'http': status, 'id': conversation}, ms)
    if not conversation:
        return report(args)

    # 2. 取 scope 与 composer_revision（提交检索需要它们与页面一致）
    status, body, ms = session.call('GET', f'/api/assistant/conversations/{conversation}')
    scope = body.get('scope') if isinstance(body, dict) else None
    composer = body.get('composer_revision') if isinstance(body, dict) else None
    record('读取会话快照', status == 200 and bool(scope) and composer is not None,
           {'http': status, 'composer_revision': composer}, ms)
    if not scope or composer is None:
        return report(args)

    # 3. 提交「检索法律资料」
    request_id = str(uuid.uuid4())
    payload = {'request_id': request_id, 'expected_scope': scope,
               'expected_composer_revision': composer, 'content': args.keyword,
               'requested_skill': 'legal_research', 'attachment_ids': []}
    status, body, ms = session.call('POST', f'/api/assistant/conversations/{conversation}/researches',
                                    payload, headers=csrf)
    run = (body or {}).get('run') or {}
    record('提交显式检索（202）', status == 202 and run.get('id') is not None,
           {'http': status, 'code': (body or {}).get('code'), 'run': run.get('id')}, ms)
    if not run.get('id'):
        return report(args)

    # 4. 等研究任务结束
    research = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status, body, ms = session.call(
            'GET', f'/api/assistant/conversations/{conversation}/researches/by-request/{request_id}')
        state = ((body or {}).get('run') or {}).get('state')
        if state in ('completed', 'failed', 'cancelled', 'interrupted', 'blocked'):
            research = body
            break
        time.sleep(0.3)
    state = ((research or {}).get('run') or {}).get('state')
    record('研究任务完成', state == 'completed', {'state': state, 'http': status}, ms)
    if state != 'completed':
        return report(args)

    receipts = research.get('receipts') or []
    result = ((receipts[0] if receipts else {}).get('result') or {}).get('result') or {}
    page = result.get('knowledge_page') or {}
    handler = (receipts[0] if receipts else {}).get('handler_id')
    law_hits = (page.get('groups') or {}).get('law') or []
    case_hits = (page.get('groups') or {}).get('case') or []
    record('回执来自只读知识服务而不是本地法库',
           handler == 'legal_knowledge.search' and result.get('tool') == 'legal_knowledge.search',
           {'handler_id': handler, 'tool': result.get('tool')})
    record('检索真的命中法条', bool(law_hits), {'law': len(law_hits), 'state': page.get('state')})
    record('页面不再宣称未连接法库',
           '本机尚未连接法律资料库' not in json.dumps(research, ensure_ascii=False),
           {'page_state': page.get('state')})

    ids = ((receipts[0] if receipts else {}).get('result') or {}).get('citation_ids') or []
    ordered = law_hits + case_hits
    record('citation_ids 与法条/案例顺序一一对应', len(ids) == len(ordered),
           {'ids': len(ids), 'citations': len(ordered)})
    if not ordered or not ids:
        return report(args)

    # 5. 打开保存的引用（原聊天里点引用走的就是这条接口）
    status, saved, ms = session.call('GET', f'/api/assistant/library-citations/{ids[0]}')
    citation = (saved or {}).get('knowledge_citation') or {}
    record('保存的引用是知识服务引用（不是伪造的本地引用）',
           status == 200 and bool(citation) and not (saved or {}).get('citation'),
           {'http': status, 'source_id': citation.get('source_id')}, ms)
    if not citation:
        return report(args)

    first = ordered[0]
    record('保存的引用与回执第一条一致',
           citation.get('source_id') == first.get('source_id')
           and citation.get('snippet', {}).get('text') == first.get('snippet', {}).get('text'),
           {'saved': citation.get('source_id'), 'receipt': first.get('source_id')})

    # 6. 带上检索时的版本回读原文
    source_id = urllib.parse.quote(citation['source_id'], safe='')
    version = citation['source_version']['sha256']
    status, original, ms = session.call(
        'GET', f'/api/knowledge/sources/{source_id}?version={version}')
    content = (original or {}).get('content') or {}
    record('按检索时的版本回读原文成功',
           status == 200 and citation['snippet']['text'] in content.get('text', ''),
           {'http': status, 'chars': len(content.get('text', ''))}, ms)
    record('回读声明的版本与检索时一致',
           (original or {}).get('source_version', {}).get('sha256') == version,
           {'returned': (original or {}).get('source_version', {}).get('sha256')})

    # 7. 版本不一致必须阻断（这是外部审计复现过的问题）
    wrong = '0' * 64
    status, blocked, ms = session.call(
        'GET', f'/api/knowledge/sources/{source_id}?version={wrong}')
    record('版本不一致被阻断（409）',
           status == 409 and (blocked or {}).get('code') == 'KNOWLEDGE_SOURCE_STALE',
           {'http': status, 'code': (blocked or {}).get('code')}, ms)

    # 8. 案例同理
    if case_hits:
        case = case_hits[0]
        status, original, ms = session.call(
            'GET', '/api/knowledge/sources/' + urllib.parse.quote(case['source_id'], safe='')
            + '?version=' + case['source_version']['sha256'])
        record('案例来源同样可回读',
               status == 200 and (original or {}).get('source_version', {}).get('sha256')
               == case['source_version']['sha256'],
               {'http': status, 'source_id': case['source_id']}, ms)

    return report(args)


def report(args) -> int:
    passed = sum(1 for item in RESULTS if item['ok'])
    total = len(RESULTS)
    output = {'base': args.base, 'keyword': args.keyword, 'steps': RESULTS,
              'passed': passed, 'total': total, 'all_passed': passed == total}
    if args.out:
        Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n{passed}/{total} 通过；all_passed={passed == total}')
    return 0 if passed == total else 1


if __name__ == '__main__':
    raise SystemExit(main())
