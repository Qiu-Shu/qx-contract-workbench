"""只读知识服务（试点）：`/v1/status`、`/v1/search`、`/v1/sources/{id}`。

为什么用标准库而不是 FastAPI
---------------------------
试点要求"服务只绑定本机回环地址、用服务端受控配置与凭据保护调用"，并且不得为跑一个
只读查询引入新的安装面。`http.server` + `sqlite3` + `json` 已经够用，且 Python 3.12/3.13
都能直接运行，不和工作台（>=3.12,<3.13）的约束打架。

安全边界
--------
- 绑定地址写死 127.0.0.1，不接受 `--bind 0.0.0.0`。
- 每个请求校验 `X-KB-Token`（常量时间比较）；令牌只从环境变量或文件读，不进 argv、不进日志。
- 来源 ID 必须是 `law_unit:unit_xxx` 或 `case_book:<案例编号>`，不存在"传路径"的入口。
- 请求体上限 8 KiB、查询 ≤200 字、limit ≤10、单次原文读取 ≤20,000 字。
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import kb_core
from kb_core import CASE_ID, CASE_PREFIX, LAW_ID, LAW_PREFIX, MAX_LIMIT, MAX_QUERY_CHARS, ServiceFault

SERVICE_NAME = 'legal-knowledge-service'
SERVICE_VERSION = '1.0.0'
MAX_BODY = 8 * 1024

DEFAULT_KB = Path(__file__).resolve().parent / 'assets' / 'legal-knowledge'
DEFAULT_CASE_ROOT = Path(__file__).resolve().parent / 'assets' / 'casebooks'

# 除常见分词空白（\t \n \r）之外的 C0/C1 控制字符
_CONTROL = re.compile(r'[\x00-\x08\x0e-\x1f\x7f-\x9f]')
_WHITESPACE = re.compile(r'[\t\n\r]')


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _heading_path(raw: str | None) -> str:
    """源库里有文档的 heading_path 存的是字面量 '[]'（上游抽取时留下的空列表）。

    直接透传会让界面渲染出「｜[]」这种残渣；这里归一为"未提供"。
    只改返回值，不动源库。
    """
    text = (raw or '').strip()
    return '' if text in {'[]', '{}', 'null', 'None'} else text


class Assets:
    """一次装载、进程内共享；装载失败就让启动失败，不带着半个库上线。"""

    def __init__(self, legal_db: Path, corpus: Path, cases: Path, case_root: Path):
        self.law = kb_core.LawIndex(legal_db)
        self.cases = kb_core.CaseIndex(corpus, cases, case_root)
        self.probe = self.law.readonly_probe()
        self.case_total = len(self.cases.anchors)
        self.case_retrievable = len(self.cases.docs)

    # ---- 引用构造 ---------------------------------------------------------
    def cite_law(self, unit_id: str, query: str) -> dict:
        hit = self.law.unit_by_id(unit_id)
        start, end, basis, line_start, line_end = self.law.locate(hit)
        raw = hit['raw_text']
        snippet = kb_core.snippet_around(raw, start, end, query)
        return {
            'source_id': LAW_PREFIX + unit_id,
            'kind': 'law',
            'title': f"{hit['doc_title']} {hit['label']}".strip(),
            'heading_path': _heading_path(hit['heading_path']),
            'source_version': {'sha256': hit['doc_sha'], 'basis': 'documents.sha256+raw_text_recomputed',
                               'verified': 'recomputed'},
            'location': {'line_start': line_start, 'line_end': line_end,
                         'char_start': start, 'char_end': end, 'basis': basis},
            'snippet': {**snippet, 'sha256': _sha256(snippet['text'])},
            'verification': {'support': 'unverified', 'applicability': 'unverified'},
        }

    def cite_case(self, case_id: str, query: str) -> dict:
        info = self.cases.cite(case_id, query)
        meta = self.cases.case_meta(case_id)
        snippet = kb_core.snippet_around(info['text'], info['block_start'], info['block_end'], query)
        return {
            'source_id': CASE_PREFIX + case_id,
            'kind': 'case',
            'title': f"{meta['volume']}｜{meta['title']}",
            'heading_path': f"{meta['cause']}｜{meta['doc_type']}",
            'source_version': {'sha256': info['sha256'], 'basis': 'anchor.md_sha256', 'verified': 'anchor_match'},
            'location': {'line_start': info['line_start'], 'line_end': info['line_end'],
                         'char_start': info['block_start'], 'char_end': info['block_end'],
                         'basis': 'anchor.char_range'},
            'snippet': {**snippet, 'sha256': _sha256(snippet['text'])},
            'metadata': {'case_no': meta['case_no'], 'court': meta['court'], 'cause': meta['cause']},
            'verification': {'support': 'unverified', 'applicability': 'unverified'},
        }

    # ---- 状态 -------------------------------------------------------------
    def status(self) -> dict:
        return {
            'service': {'name': SERVICE_NAME, 'version': SERVICE_VERSION},
            'state': 'ready',
            'readonly': {
                'legal_db': {'mode': 'ro', 'pragma_query_only': True,
                             'write_attempt_blocked': self.probe.get('write_blocked', False)},
                'cases': {'mode': 'read_only_files', 'hash_checked': True},
            },
            'assets': {
                'law': {'documents': self.law.documents, 'units': self.law.units},
                'cases': {'cases': self.case_total, 'retrieval_documents': self.case_retrievable},
            },
            'rankers': {
                'law': 'sqlite_fts5_bm25_trigram（短查询退化为 rowid 分块 LIKE）',
                'case': 'bm25_char_bigram_v1',
                'linear_ranker': {
                    'enabled': False,
                    'version': None,
                    'reason': '试点未启用已验收线性权重：该权重的 8 维特征与在线检索路径未做逐维对齐，'
                              '贸然加载会把"权重已验收"说成"这条链路已验收"',
                },
            },
            'limits': {'query_chars': MAX_QUERY_CHARS, 'limit': MAX_LIMIT,
                       'snippet_chars': kb_core.MAX_SNIPPET_CHARS,
                       'source_chars': kb_core.MAX_SOURCE_CHARS, 'body_bytes': MAX_BODY},
        }


class Application:
    def __init__(self, assets: Assets, token: str):
        self.assets = assets
        self.token = token

    # ---- 路由 -------------------------------------------------------------
    def handle(self, method: str, path: str, query: dict, body: bytes, headers) -> tuple[int, dict]:
        try:
            self._authorize(headers)
            if method == 'GET' and path == '/v1/status':
                return 200, self.assets.status()
            if method == 'POST' and path == '/v1/search':
                return 200, self._search(body)
            match = re.fullmatch(r'/v1/sources/(.+)', path)
            if method == 'GET' and match:
                return 200, self._source(match.group(1), query)
            raise ServiceFault('BAD_REQUEST', '未知路径或方法')
        except ServiceFault as fault:
            return fault.status, {'code': fault.code, 'message': fault.message}
        except Exception as error:  # noqa: BLE001 - 兜底也要给出稳定错误码
            return 500, {'code': 'INTERNAL', 'message': f'服务内部错误：{type(error).__name__}'}

    def _authorize(self, headers) -> None:
        presented = headers.get('X-KB-Token') or ''
        if not presented:
            auth = headers.get('Authorization') or ''
            if auth.startswith('Bearer '):
                presented = auth[7:]
        if not presented or not hmac.compare_digest(presented, self.token):
            raise ServiceFault('UNAUTHORIZED', '缺少或错误的服务凭据')

    def _search(self, body: bytes) -> dict:
        if len(body) > MAX_BODY:
            raise ServiceFault('BAD_REQUEST', '请求体超限')
        try:
            payload = json.loads(body or b'{}')
        except ValueError:
            raise ServiceFault('BAD_REQUEST', '请求体不是合法 JSON') from None
        if not isinstance(payload, dict):
            raise ServiceFault('BAD_REQUEST', '请求体必须是对象')
        query = payload.get('query')
        if not isinstance(query, str):
            raise ServiceFault('QUERY_INVALID', 'query 必须是字符串')
        query = query.strip()
        if not query:
            raise ServiceFault('QUERY_INVALID', 'query 不能为空')
        if len(query) > MAX_QUERY_CHARS:
            raise ServiceFault('QUERY_INVALID', f'query 超过 {MAX_QUERY_CHARS} 字')
        # 制表/换行是合法的分词空白，其余控制字符没有语义；过去它们会被
        # 静默归一掉再返回 empty，看起来和"库里没有"一模一样。这里直接拒绝。
        if _CONTROL.search(query):
            raise ServiceFault('QUERY_INVALID', 'query 含控制字符')
        query = _WHITESPACE.sub(' ', query)
        kinds = payload.get('kinds') or ['law', 'case']
        if (not isinstance(kinds, list) or not kinds
                or any(kind not in ('law', 'case') for kind in kinds)):
            raise ServiceFault('BAD_REQUEST', 'kinds 只能取 law / case')
        limit = payload.get('limit', 3)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
            raise ServiceFault('BAD_REQUEST', f'limit 必须是 1..{MAX_LIMIT} 的整数')

        started = time.monotonic()
        groups: dict[str, list] = {'law': [], 'case': []}
        notes: list[str] = []
        degraded: list[dict] = []

        if 'law' in kinds:
            rows, channel, partial = self.assets.law.search(query, limit)
            for row in rows:
                cite = self.assets.cite_law(row['unit_id'], query)
                cite['score'] = round(row['score'], 6)
                cite['score_basis'] = channel
                groups['law'].append(cite)
            if partial:
                degraded.append({'kind': 'law', 'code': 'SCAN_BUDGET_PARTIAL',
                                 'message': '短查询走分块扫描，已到时间预算但未扫完全库；'
                                            '结果只是已扫范围内的命中，不代表全库只有这些'})
            notes.append(f'法条检索通道：{channel}')

        if 'case' in kinds:
            hits = self.assets.cases.search(query, limit)
            relaxed = False
            for hit in hits:
                cite = self.assets.cite_case(hit['case_id'], query)
                cite['score'] = hit['score']
                cite['score_basis'] = 'bm25_char_bigram_v1'
                relaxed = relaxed or bool(hit.get('relaxed'))
                groups['case'].append(cite)
            notes.append('案例检索通道：bm25_char_bigram_v1（对清洗语料打分，引用取原文）')
            if relaxed:
                degraded.append({'kind': 'case', 'code': 'MATCH_RELAXED',
                                 'message': '没有案例同时包含全部检索段，已放宽为"过半段落命中"，'
                                            '结果只作线索，不等于精确匹配'})

        notes.append('法条分数来自 SQLite FTS5 bm25，案例分数来自自算 BM25，两者口径不同，故分组呈现、不合并排序。')

        total = len(groups['law']) + len(groups['case'])
        return {
            'state': 'ready' if total else 'empty',
            'query': query,
            'grouped': True,
            'groups': groups,
            'notes': notes,
            'degraded': degraded,
            'elapsed_ms': round(1000 * (time.monotonic() - started), 1),
        }

    def _source(self, source_id: str, query: dict) -> dict:
        source_id = unquote(source_id)
        started = time.monotonic()
        if source_id.startswith(LAW_PREFIX):
            unit_id = source_id[len(LAW_PREFIX):]
            if not LAW_ID.fullmatch(unit_id):
                raise ServiceFault('BAD_REQUEST', '法条来源标识格式不正确')
            hit = self.assets.law.unit_by_id(unit_id)
            start, end, basis, line_start, line_end = self.assets.law.locate(hit)
            text = hit['raw_text']
            title = f"{hit['doc_title']} {hit['label']}".strip()
            sha = hit['doc_sha']
            version_basis = 'documents.sha256+raw_text_recomputed'
            version_verified = 'recomputed'
        elif source_id.startswith(CASE_PREFIX):
            case_id = source_id[len(CASE_PREFIX):]
            if not CASE_ID.fullmatch(case_id):
                raise ServiceFault('BAD_REQUEST', '案例来源标识格式不正确')
            info = self.assets.cases.cite(case_id, '')
            text, start, end = info['text'], info['block_start'], info['block_end']
            meta = self.assets.cases.case_meta(case_id)
            title = f"{meta['volume']}｜{meta['title']}"
            sha = info['sha256']
            version_basis = 'anchor.md_sha256'
            version_verified = 'anchor_match'
            line_start, line_end = info['line_start'], info['line_end']
            basis = 'anchor.char_range'
        else:
            raise ServiceFault('BAD_REQUEST', '只接受 law_unit: / case_book: 前缀的来源标识')

        # 检索时看到的是哪一版，回读时就必须还是哪一版。只比 source_id 不够——
        # 原文换了、重新登记了，source_id 一个字都不变，引用内容却已经换人了。
        expected = self._expected_version(query)
        if expected is not None and not hmac.compare_digest(expected, sha):
            raise ServiceFault('SOURCE_STALE',
                               '检索时的来源版本与本次回读的登记版本不一致，已阻断；请重新检索后再引用')

        window = self._range(query, start, end, len(text))
        clipped = kb_core.clip(text, window[0], window[1])
        return {
            'source_id': source_id,
            'title': title,
            'source_version': {'sha256': sha, 'basis': version_basis, 'verified': version_verified},
            'location': {'line_start': line_start, 'line_end': line_end,
                         'char_start': start, 'char_end': end, 'basis': basis},
            'whole_block': {'start': start, 'end': end},
            'content': {**clipped, 'sha256': _sha256(clipped['text'])},
            'verification': {'support': 'unverified', 'applicability': 'unverified'},
            'elapsed_ms': round(1000 * (time.monotonic() - started), 1),
        }

    @staticmethod
    def _expected_version(query: dict) -> str | None:
        """调用方带过来的"检索时版本"。格式不对直接拒，不猜。"""
        raw = (query.get('version') or [None])[0]
        if raw is None or raw == '':
            return None
        if not re.fullmatch(r'[0-9a-f]{64}', raw):
            raise ServiceFault('BAD_REQUEST', 'version 必须是 64 位小写 sha256')
        return raw

    @staticmethod
    def _range(query: dict, start: int, end: int, length: int) -> tuple[int, int]:
        raw_start = query.get('start', [None])[0]
        raw_end = query.get('end', [None])[0]
        if raw_start is None and raw_end is None:
            return start, end
        try:
            wanted_start = int(raw_start) if raw_start is not None else start
            wanted_end = int(raw_end) if raw_end is not None else end
        except (TypeError, ValueError):
            raise ServiceFault('BAD_REQUEST', 'start / end 必须是整数') from None
        if not 0 <= wanted_start < wanted_end <= length:
            raise ServiceFault('RANGE_INVALID', f'请求范围必须在 0..{length} 之间且 start<end')
        if wanted_start < start or wanted_end > end:
            raise ServiceFault('RANGE_INVALID', '请求范围超出来源块边界，拒绝越界读取')
        return wanted_start, wanted_end


def make_handler(app: Application):
    class Handler(BaseHTTPRequestHandler):
        server_version = f'{SERVICE_NAME}/{SERVICE_VERSION}'
        protocol_version = 'HTTP/1.1'

        def _dispatch(self, method: str):
            parts = urlsplit(self.path)
            body = b''
            if method == 'POST':
                length = int(self.headers.get('Content-Length') or 0)
                if length > MAX_BODY:
                    self._send(413, {'code': 'BAD_REQUEST', 'message': '请求体超限'})
                    return
                body = self.rfile.read(length)
            status, payload = app.handle(method, parts.path, parse_qs(parts.query), body, self.headers)
            self._send(status, payload)

        def _send(self, status: int, payload: dict):
            blob = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(blob)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(blob)

        def do_GET(self):
            self._dispatch('GET')

        def do_POST(self):
            self._dispatch('POST')

        def log_message(self, fmt, *args):  # 只记方法/路径/状态，不记查询内容与凭据
            sys.stderr.write('%s %s\n' % (self.command, urlsplit(self.path).path))

    return Handler


def build_server(assets: Assets, token: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(Application(assets, token)))
    server.daemon_threads = True
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='只读知识服务（试点）')
    parser.add_argument('--legal-db', type=Path, default=DEFAULT_KB / 'data' / 'legal.sqlite')
    parser.add_argument('--corpus', type=Path,
                        default=DEFAULT_KB / 'model_lab/casebook_2026_20261101/data/corpus.jsonl')
    parser.add_argument('--cases', type=Path,
                        default=DEFAULT_KB / 'model_lab/casebook_2026_20261101/data/cases.jsonl')
    parser.add_argument('--case-root', type=Path, default=DEFAULT_CASE_ROOT)
    parser.add_argument('--port', type=int, default=0, help='0 表示由系统分配空闲端口')
    parser.add_argument('--token-env', default='KB_SERVICE_TOKEN')
    args = parser.parse_args(argv)

    token = os.environ.get(args.token_env, '')
    if len(token) < 16:
        print(f'缺少服务凭据：请设置环境变量 {args.token_env}（至少 16 字符）', file=sys.stderr)
        return 2
    for path, label in ((args.legal_db, '法条库'), (args.corpus, '案例语料'),
                        (args.cases, '案例清单')):
        if not path.exists():
            print(f'{label}不存在：{path}', file=sys.stderr)
            return 3
    if not args.case_root.exists():
        print(f'案例原文目录不存在：{args.case_root}', file=sys.stderr)
        return 3

    started = time.monotonic()
    try:
        assets = Assets(args.legal_db, args.corpus, args.cases, args.case_root)
    except ServiceFault as fault:
        # 库结构/IO 有问题就别上线：带着半个库启动，只会把故障推迟成"查询没结果"。
        print(f'装载失败[{fault.code}]：{fault.message}', file=sys.stderr)
        return 5
    if not assets.probe.get('write_blocked'):
        print('只读自检失败：向源库写入未被阻止，拒绝启动', file=sys.stderr)
        return 4
    server = build_server(assets, token, args.port)
    host, port = server.server_address
    boot_ms = round(1000 * (time.monotonic() - started), 1)
    print(json.dumps({'event': 'listening', 'host': host, 'port': port,
                      'pid': os.getpid(), 'boot_ms': boot_ms,
                      'service': SERVICE_NAME, 'version': SERVICE_VERSION},
                     ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
