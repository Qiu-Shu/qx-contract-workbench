"""服务级测试：独立虚构语料 + 真实 HTTP 请求。

只用一个 MockTransport 或静态页面不能证明接通，所以这里起真进程：
`kb_service.main()` 在子线程里跑真实的 ThreadingHTTPServer，用 urllib 发真实请求。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import kb_core  # noqa: E402
import kb_service  # noqa: E402

TOKEN = 'pilot-test-token-0123456789'

LAW_DOCS = [
    ('doc_fixture_0001', '+虚构省买卖合同条例', 3, [
        ('unit_000000000000000000000001', '第三条', 3, 4,
         '第三条\u3000出卖人交付的标的物不符合质量要求的，买受人可以请求减少价款或者要求修理、更换。'),
        ('unit_000000000000000000000002', '第四条', 5, 6,
         '第四条\u3000当事人约定违约金的，违约金过分高于造成的损失的，可以请求适当减少。'),
    ]),
    ('doc_fixture_0002', '+虚构市定金管理办法', 2, [
        ('unit_000000000000000000000003', '第一条', 3, 4,
         '第一条\u3000定金合同自实际交付定金时成立。'),
    ]),
]

CASE_BODY = """# 2026年度案例【虚构买卖纠纷】

## 一、标的物质量

### 1. 交付标的物存在质量瑕疵时减价请求的认定

——虚构原告甲诉虚构被告乙买卖合同案

#### 基本案情

虚构原告甲向虚构被告乙购买一批虚构设备，交付后发现有质量瑕疵，双方就减价发生争议。

#### 法院裁判要旨

法院认为，标的物存在质量瑕疵致使不能实现合同目的的，买受人可以请求减少价款；
减少的数额应当以实际损失为基础确定。

#### 法官后语

本案的裁判要旨在于把质量瑕疵与减价请求之间的关系讲清楚。
"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build_fixture(root: Path) -> dict:
    """造一套与真实库同构的最小语料：法条库 + 案例清单 + 原文 Markdown。"""
    db = root / 'legal.sqlite'
    conn = sqlite3.connect(db)
    conn.executescript("""
        create table meta(key text primary key, value text not null);
        create table documents(id text primary key, sha256 text unique not null, title text not null,
            filename_date text, raw_text text not null, metadata text not null, active integer not null default 1);
        create table sources(path text primary key, relative_path text not null, doc_id text,
            sha256 text, size integer, mtime_ns integer, state text not null, error text,
            title text, filename_date text);
        create table units(id text primary key, doc_id text not null, unit_key text not null,
            label text not null, kind text not null, start_line integer not null, end_line integer not null,
            heading_path text not null, text text not null, rule_cues text not null);
        create virtual table units_fts using fts5(title, label, text, tokenize='trigram');
    """)
    for doc_id, title, _n, units in LAW_DOCS:
        lines = ['（虚构文件）', '', title]
        for _uid, label, start, end, text in units:
            while len(lines) < start - 1:
                lines.append('')
            lines.extend(text.split('\n')[: max(1, end - start)])
        raw = '\n'.join(lines) + '\n'
        conn.execute('insert into documents values (?,?,?,?,?,?,?)',
                     (doc_id, _sha(raw), title, None, raw, '{}', 1))
        for uid, label, start, end, text in units:
            conn.execute('insert into units values (?,?,?,?,?,?,?,?,?,?)',
                         (uid, doc_id, label, label, 'article', start, end, '["虚构总则"]', text, '[]'))
            conn.execute('insert into units_fts (title, label, text) values (?,?,?)', (title, label, text))
    conn.commit()
    conn.close()

    books = root / 'books'
    volume = '2026年度案例【虚构买卖纠纷】'
    md_rel = f'{volume}/{volume}.md'
    md_path = books / md_rel
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(CASE_BODY, encoding='utf-8')

    # 锚点按真实口径算：行区间 + 换算出的字符区间
    lines = CASE_BODY.split('\n')
    line_start, line_end = 7, 15
    char_start = sum(len(x) + 1 for x in lines[:line_start - 1])
    char_end = min(sum(len(x) + 1 for x in lines[:line_end]), len(CASE_BODY))
    case_id = '2026年度案例【虚构买卖纠纷】#001'
    cases = [{
        'case_id': case_id, 'volume': volume, 'volume_index': 1, 'chapter': '一、标的物质量',
        'title': '交付标的物存在质量瑕疵时减价请求的认定',
        'subtitle': '——虚构原告甲诉虚构被告乙买卖合同案', 'cause': '买卖合同纠纷',
        'doc_type': '民事判决书', 'case_no': '(2026)虚01民终1号', 'case_no_year': 2026,
        'court': '虚构市中级人民法院', 'judgment_date': None, 'parties_raw': '虚构原告甲；虚构被告乙',
        'sections_present': ['基本案情', '法院裁判要旨'], 'facts_chars': 1, 'focus_chars': 1,
        'reasoning_chars': 1, 'comment_chars': 1, 'statutes_cited': [], 'statutes_n': 0,
        'anchor': {'md_rel': md_rel, 'md_sha256': _sha(CASE_BODY), 'line_start': line_start,
                   'line_end': line_end, 'char_start': char_start, 'char_end': char_end,
                   'char_basis': 'unicode 码点', 'toc_page': 1, 'pdf_page': 1,
                   'pdf_page_verified': True, 'pdf_page_method': 'case_no', 'pdf_sha256': _sha('pdf')},
    }]
    (root / 'cases.jsonl').write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in cases) + '\n',
                                      encoding='utf-8')
    corpus = [{
        'case_id': case_id, 'volume': volume, 'title': '交付标的物存在质量瑕疵时减价请求的认定',
        'cause': '买卖合同纠纷', 'line_start': line_start, 'line_end': line_end, 'md_rel': md_rel,
        'text': '法院认为，标的物存在质量瑕疵致使不能实现合同目的的，买受人可以请求减少价款；'
                '减少的数额应当以实际损失为基础确定。',
    }]
    (root / 'corpus.jsonl').write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in corpus) + '\n',
                                       encoding='utf-8')
    return {'db': db, 'corpus': root / 'corpus.jsonl', 'cases': root / 'cases.jsonl',
            'books': books, 'md_path': md_path, 'case_id': case_id, 'md_rel': md_rel}


class ServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix='kb-pilot-test-'))
        cls.fx = build_fixture(cls.root)
        cls.assets = kb_service.Assets(cls.fx['db'], cls.fx['corpus'], cls.fx['cases'], cls.fx['books'])
        cls.server = kb_service.build_server(cls.assets, TOKEN, 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        shutil.rmtree(cls.root, ignore_errors=True)

    # ---- HTTP 辅助 --------------------------------------------------------
    def call(self, method, path, payload=None, token=TOKEN):
        url = f'http://127.0.0.1:{self.port}{path}'
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        if token:
            request.add_header('X-KB-Token', token)
        if data is not None:
            request.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    # ---- 1. 状态与只读自证 -----------------------------------------------
    def test_status_reports_real_counts_and_readonly(self):
        status, body = self.call('GET', '/v1/status')
        self.assertEqual(status, 200)
        self.assertEqual(body['assets']['law']['documents'], 2)
        self.assertEqual(body['assets']['law']['units'], 3)
        self.assertEqual(body['assets']['cases']['cases'], 1)
        self.assertTrue(body['readonly']['legal_db']['write_attempt_blocked'])
        self.assertFalse(body['rankers']['linear_ranker']['enabled'])

    def test_source_database_rejects_writes(self):
        path = self.fx['db']
        ro = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        with self.assertRaises(sqlite3.Error):
            ro.execute("insert into meta(key,value) values('x','y')")
        ro.close()
        # 索引本身可写时，服务连接也必须挡住
        rw = sqlite3.connect(path)
        before = rw.execute('select count(*) from meta').fetchone()[0]
        rw.close()
        index = kb_core.LawIndex(path)
        with self.assertRaises(sqlite3.Error):
            with index._connect() as conn:
                conn.execute("insert into meta(key,value) values('x','y')")
        rw = sqlite3.connect(path)
        self.assertEqual(rw.execute('select count(*) from meta').fetchone()[0], before)
        rw.close()

    # ---- 2. 真实检索与原文回读 -------------------------------------------
    def test_law_search_returns_quote_from_raw_text(self):
        status, body = self.call('POST', '/v1/search', {'query': '违约金', 'kinds': ['law'], 'limit': 3})
        self.assertEqual(status, 200)
        self.assertEqual(body['state'], 'ready')
        cite = body['groups']['law'][0]
        self.assertTrue(cite['source_id'].startswith('law_unit:'))
        loc = cite['location']
        self.assertLess(loc['char_start'], loc['char_end'])
        snippet = cite['snippet']
        self.assertIn(snippet['text'], cite and self.assets.law.unit_by_id(cite['source_id'].split(':', 1)[1])['raw_text'])
        self.assertEqual(hashlib.sha256(snippet['text'].encode()).hexdigest(), snippet['sha256'])

    def test_case_search_quote_comes_from_original_markdown(self):
        status, body = self.call('POST', '/v1/search',
                                 {'query': '质量瑕疵 减价', 'kinds': ['case'], 'limit': 3})
        self.assertEqual(status, 200)
        cite = body['groups']['case'][0]
        self.assertEqual(cite['source_id'], f'case_book:{self.fx["case_id"]}')
        original = self.fx['md_path'].read_text(encoding='utf-8')
        snippet = cite['snippet']
        self.assertIn(snippet['text'], original)
        self.assertGreaterEqual(snippet['start'], cite['location']['char_start'])
        self.assertLessEqual(snippet['end'], cite['location']['char_end'])
        self.assertEqual(hashlib.sha256(snippet['text'].encode()).hexdigest(), snippet['sha256'])

    def test_read_source_returns_same_bytes(self):
        _, search = self.call('POST', '/v1/search', {'query': '质量瑕疵', 'kinds': ['case'], 'limit': 1})
        source_id = search['groups']['case'][0]['source_id']
        status, body = self.call('GET', f'/v1/sources/{urllib.parse.quote(source_id, safe="")}')
        self.assertEqual(status, 200)
        original = self.fx['md_path'].read_text(encoding='utf-8')
        self.assertEqual(body['content']['text'], original[body['content']['start']:body['content']['end']])
        self.assertEqual(body['content']['sha256'], hashlib.sha256(body['content']['text'].encode()).hexdigest())

    def test_empty_result_is_not_an_error(self):
        status, body = self.call('POST', '/v1/search', {'query': '完全不存在的词条组合', 'limit': 3})
        self.assertEqual(status, 200)
        self.assertEqual(body['state'], 'empty')
        self.assertEqual(body['groups']['law'], [])
        self.assertEqual(body['groups']['case'], [])

    # ---- 3. 拒绝面 --------------------------------------------------------
    def test_requires_token(self):
        status, body = self.call('GET', '/v1/status', token=None)
        self.assertEqual(status, 401)
        self.assertEqual(body['code'], 'UNAUTHORIZED')
        status, body = self.call('GET', '/v1/status', token='wrong-token-000000')
        self.assertEqual(status, 401)

    def test_rejects_malicious_source_ids(self):
        for bad in ['../..%2Fetc%2Fpasswd', 'law_unit:../../etc/passwd', 'case_book:../../x',
                    'file:/etc/passwd', 'law_unit:unit_zzzz', 'sqlite:data/legal.sqlite']:
            status, body = self.call('GET', f'/v1/sources/{urllib.parse.quote(bad, safe="")}')
            self.assertIn(status, (400, 404), f'{bad} -> {status}')
            self.assertIn(body['code'], ('BAD_REQUEST', 'SOURCE_NOT_FOUND'))

    def test_heading_path_placeholder_is_normalised(self):
        # 源库里部分文档的 heading_path 存的是字面量 '[]'，不能原样出现在界面
        for query in ('违约金', '定金'):
            _, page = self.call('POST', '/v1/search', {'query': query, 'kinds': ['law'], 'limit': 5})
            for cite in page['groups']['law']:
                self.assertNotIn('[]', cite['heading_path'], cite['source_id'])

    def test_rejects_illegal_queries(self):
        for payload, code in [({'query': ''}, 'QUERY_INVALID'),
                              ({'query': '   '}, 'QUERY_INVALID'),
                              ({'query': '长' * 201}, 'QUERY_INVALID'),
                              # 控制字符过去被静默归一后返回 empty，与"库里没有"无法区分
                              ({'query': '\u0000违约金'}, 'QUERY_INVALID'),
                              ({'query': '违约金\u0001过高'}, 'QUERY_INVALID'),
                              ({'query': '违约金', 'limit': 0}, 'BAD_REQUEST'),
                              ({'query': '违约金', 'limit': 99}, 'BAD_REQUEST'),
                              ({'query': '违约金', 'kinds': ['graph']}, 'BAD_REQUEST'),
                              ({'query': '违约金', 'limit': True}, 'BAD_REQUEST')]:
            status, body = self.call('POST', '/v1/search', payload)
            self.assertIn(status, (400, 422), f'{payload} -> {status}')
            self.assertEqual(body['code'], code, payload)

    def test_tab_and_newline_are_treated_as_separators(self):
        # 尾部/中间的 tab、换行都归一分词空白，不该被当成控制字符拒掉
        status, body = self.call('POST', '/v1/search', {'query': '违约金\n\t', 'kinds': ['law']})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['query'], '违约金')
        self.assertEqual(body['state'], 'ready')
        status, body = self.call('POST', '/v1/search', {'query': '违约金\t过高', 'kinds': ['law']})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['query'], '违约金 过高')
        self.assertNotIn('\t', body['query'])

    def test_rejects_forged_range(self):
        _, search = self.call('POST', '/v1/search', {'query': '违约金', 'kinds': ['law'], 'limit': 1})
        cite = search['groups']['law'][0]
        source_id = cite['source_id']
        for start, end in [(-1, 10), (10, 5), (0, 10 ** 9),
                           (cite['location']['char_start'] - 1, cite['location']['char_start'] + 5)]:
            status, body = self.call('GET', f'/v1/sources/{urllib.parse.quote(source_id, safe="")}?start={start}&end={end}')
            self.assertEqual(status, 409, f'{start}-{end}')
            self.assertEqual(body['code'], 'RANGE_INVALID')

    def test_missing_material_is_distinguished(self):
        status, body = self.call('GET', '/v1/sources/law_unit:unit_ffffffffffffffffffffffff')
        self.assertEqual(status, 404)
        self.assertEqual(body['code'], 'SOURCE_NOT_FOUND')
        status, body = self.call('GET', '/v1/sources/' + urllib.parse.quote('case_book:2026年度案例【查无此册】#999', safe=''))
        self.assertEqual(status, 404)
        self.assertEqual(body['code'], 'SOURCE_NOT_FOUND')

    def test_stale_original_is_blocked(self):
        # 改坏原文但不改大小写不到的字节：hash 必然变，引用必须被阻断
        target = self.fx['md_path']
        backup = target.read_text(encoding='utf-8')
        try:
            target.write_text(backup.replace('法院认为', '法院认定'), encoding='utf-8')
            status, body = self.call('POST', '/v1/search',
                                     {'query': '质量瑕疵', 'kinds': ['case'], 'limit': 1})
            self.assertEqual(status, 409)
            self.assertEqual(body['code'], 'SOURCE_STALE')
        finally:
            target.write_text(backup, encoding='utf-8')
        status, _ = self.call('POST', '/v1/search', {'query': '质量瑕疵', 'kinds': ['case'], 'limit': 1})
        self.assertEqual(status, 200)

    # ---- 4. 契约形状 ------------------------------------------------------
    def test_response_declares_both_groups_and_score_basis(self):
        _, body = self.call('POST', '/v1/search', {'query': '质量瑕疵', 'limit': 2})
        self.assertTrue(body['grouped'])
        self.assertEqual(set(body['groups']), {'law', 'case'})
        for group in ('law', 'case'):
            for cite in body['groups'][group]:
                self.assertIn('score_basis', cite)
                self.assertEqual(cite['verification']['support'], 'unverified')
                self.assertEqual(cite['verification']['applicability'], 'unverified')
        self.assertTrue(any('不合并排序' in note for note in body['notes']))

    def test_short_query_falls_back_and_says_so(self):
        _, body = self.call('POST', '/v1/search', {'query': '定金', 'kinds': ['law'], 'limit': 2})
        self.assertEqual(body['state'], 'ready')
        self.assertEqual(body['groups']['law'][0]['score_basis'], 'like_bounded')
        self.assertTrue(any('like_bounded' in note for note in body['notes']))


# ---------------------------------------------------------------------------
# 修复轮新增：外部复验独立复现的四类缺陷
#
# 这一组刻意不共用 `ServiceTest` 的夹具——它们要改库、要造重复正文、要删表，
# 共用会把"故障"传染给前 16 项正常路径检查。每个用例自己起一份最小语料与端口。
# ---------------------------------------------------------------------------

DUP_LINES = ['（虚构文件）', '重复条文正文', '中间文字', '重复条文正文', '尾部']
DUP_TEXT = '重复条文正文'
DUP_DOC_ID = 'doc_fixture_dup00'


def build_duplicate_fixture(root: Path, unit_start_line: int, unit_end_line: int) -> dict:
    """一份正文里出现两次相同条文的法条库，单元登记在指定行区间。

    `unit_start_line` 就是 `units.start_line`（1-based），与真实库口径一致。
    """
    db = root / 'legal.sqlite'
    conn = sqlite3.connect(db)
    conn.executescript("""
        create table meta(key text primary key, value text not null);
        create table documents(id text primary key, sha256 text unique not null, title text not null,
            filename_date text, raw_text text not null, metadata text not null, active integer not null default 1);
        create table units(id text primary key, doc_id text not null, unit_key text not null,
            label text not null, kind text not null, start_line integer not null, end_line integer not null,
            heading_path text not null, text text not null, rule_cues text not null);
        create virtual table units_fts using fts5(title, label, text, tokenize='trigram');
    """)
    raw = '\n'.join(DUP_LINES) + '\n'
    conn.execute('insert into documents values (?,?,?,?,?,?,?)',
                 (DUP_DOC_ID, _sha(raw), '+虚构重复条文条例', None, raw, '{}', 1))
    conn.execute('insert into units values (?,?,?,?,?,?,?,?,?,?)',
                 ('unit_d00d00000000000000000001', DUP_DOC_ID, 'dup', 'dup', 'article',
                  unit_start_line, unit_end_line, '', DUP_TEXT, '[]'))
    conn.execute('insert into units_fts (title, label, text) values (?,?,?)',
                 ('+虚构重复条文条例', 'dup', DUP_TEXT))
    conn.commit()
    conn.close()

    books = root / 'books'
    books.mkdir(parents=True, exist_ok=True)
    case_id = '2026年度案例【虚构空白】#001'
    (root / 'cases.jsonl').write_text(json.dumps({
        'case_id': case_id, 'volume': 'v', 'title': 't', 'cause': '', 'doc_type': '',
        'anchor': {'md_rel': 'v/v.md', 'md_sha256': _sha('x'), 'line_start': 1, 'line_end': 1,
                   'char_start': 0, 'char_end': 1},
    }, ensure_ascii=False) + '\n', encoding='utf-8')
    (root / 'corpus.jsonl').write_text('', encoding='utf-8')
    return {'db': db, 'corpus': root / 'corpus.jsonl', 'cases': root / 'cases.jsonl',
            'books': books, 'raw': raw}


MIS_LINES = ['标题', '唯一条文正文', '尾部']
MIS_TEXT = '唯一条文正文'
MIS_UNIT_ID = 'unit_d00d00000000000000000002'


def build_misregistered_line_fixture(root: Path) -> dict:
    """正文里文本唯一，但单元登记的 `start_line/end_line` 指错了位置。

    这个形态在真实库里来自抽取脚本按段落序号反推行号时的错位：文本、文档哈希都
    没错，只有行号错了。定位器只能靠唯一文本命中拿到偏移；如果这时仍旧回传登记
    行号，卡片会写"第 3 行"，而字符偏移落在第 2 行——同一份引用自己打自己。
    """
    db = root / 'legal.sqlite'
    conn = sqlite3.connect(db)
    conn.executescript("""
        create table meta(key text primary key, value text not null);
        create table documents(id text primary key, sha256 text unique not null, title text not null,
            filename_date text, raw_text text not null, metadata text not null, active integer not null default 1);
        create table units(id text primary key, doc_id text not null, unit_key text not null,
            label text not null, kind text not null, start_line integer not null, end_line integer not null,
            heading_path text not null, text text not null, rule_cues text not null);
        create virtual table units_fts using fts5(title, label, text, tokenize='trigram');
    """)
    raw = '\n'.join(MIS_LINES) + '\n'
    doc_id = 'doc_fixture_mis00'
    conn.execute('insert into documents values (?,?,?,?,?,?,?)',
                 (doc_id, _sha(raw), '+虚构唯一文本条例', None, raw, '{}', 1))
    # 登记 3–3，实际文本在第 2 行
    conn.execute('insert into units values (?,?,?,?,?,?,?,?,?,?)',
                 (MIS_UNIT_ID, doc_id, 'mis', 'mis', 'article', 3, 3, '', MIS_TEXT, '[]'))
    conn.execute('insert into units_fts (title, label, text) values (?,?,?)',
                 ('+虚构唯一文本条例', 'mis', MIS_TEXT))
    conn.commit()
    conn.close()

    books = root / 'books'
    books.mkdir(parents=True, exist_ok=True)
    case_id = '2026年度案例【虚构空白】#002'
    (root / 'cases.jsonl').write_text(json.dumps({
        'case_id': case_id, 'volume': 'v', 'title': 't', 'cause': '', 'doc_type': '',
        'anchor': {'md_rel': 'v/v.md', 'md_sha256': _sha('x'), 'line_start': 1, 'line_end': 1,
                   'char_start': 0, 'char_end': 1},
    }, ensure_ascii=False) + '\n', encoding='utf-8')
    (root / 'corpus.jsonl').write_text('', encoding='utf-8')
    return {'db': db, 'corpus': root / 'corpus.jsonl', 'cases': root / 'cases.jsonl',
            'books': books, 'raw': raw}


class _IsolatedService:
    """每个用例一份语料 + 一个真实端口的服务，用完即拆。"""

    def __init__(self, test: unittest.TestCase, fixture: dict):
        self.test = test
        self.fixture = fixture
        self.assets = kb_service.Assets(fixture['db'], fixture['corpus'],
                                        fixture['cases'], fixture['books'])
        self.server = kb_service.build_server(self.assets, TOKEN, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def call(self, method, path, payload=None):
        url = f'http://127.0.0.1:{self.port}{path}'
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header('X-KB-Token', TOKEN)
        if data is not None:
            request.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class RepairBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='kb-pilot-repair-'))
        self._services = []

    def tearDown(self):
        for service in self._services:
            service.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _serve(self, fixture):
        service = _IsolatedService(self, fixture)
        self._services.append(service)
        return service

    # -- 缺陷 2：原文被改后仍报"版本一致" ---------------------------------
    def test_changed_raw_text_blocks_source_read(self):
        fx = build_fixture(self.root)
        service = self._serve(fx)
        # 只改 raw_text，不动 documents.sha256：这正是"登记值与实际原文脱节"的形态
        rw = sqlite3.connect(fx['db'])
        original = rw.execute('select raw_text from documents where id=?',
                              (LAW_DOCS[0][0],)).fetchone()[0]
        rw.execute('update documents set raw_text=? where id=?',
                   (original.replace('买受人', '买受人（篡改）'), LAW_DOCS[0][0]))
        rw.commit()
        rw.close()

        status, body = service.call('GET', '/v1/sources/law_unit:unit_000000000000000000000001')
        self.assertEqual(status, 409, f'原文被改却返回 {status} {body}')
        self.assertEqual(body['code'], 'SOURCE_STALE')

    def test_source_read_rejects_version_mismatch(self):
        fx = build_fixture(self.root)
        service = self._serve(fx)
        source_id = 'law_unit:unit_000000000000000000000001'
        _, ok = service.call('GET', f'/v1/sources/{source_id}')
        real = ok['source_version']['sha256']

        # 检索时拿到的版本与回读时登记的版本不一致，必须阻断而不是照旧显示"校验通过"
        status, body = service.call('GET', f'/v1/sources/{source_id}?version={"0" * 64}')
        self.assertEqual(status, 409, f'版本不一致却返回 {status} {body}')
        self.assertEqual(body['code'], 'SOURCE_STALE')

        status, body = service.call('GET', f'/v1/sources/{source_id}?version={real}')
        self.assertEqual(status, 200, body)
        self.assertEqual(body['source_version']['sha256'], real)
        self.assertTrue(body['source_version'].get('verified'))

    def test_source_read_reports_recomputed_hash(self):
        fx = build_fixture(self.root)
        service = self._serve(fx)
        _, body = service.call('GET', '/v1/sources/law_unit:unit_000000000000000000000001')
        rw = sqlite3.connect(fx['db'])
        raw = rw.execute('select raw_text from documents where id=?', (LAW_DOCS[0][0],)).fetchone()[0]
        rw.close()
        self.assertEqual(body['source_version']['sha256'], _sha(raw))

    # -- 缺陷 3：重复正文被定位到第一次出现处 ------------------------------
    def test_duplicate_text_located_by_registered_line(self):
        fx = build_duplicate_fixture(self.root, 4, 4)
        service = self._serve(fx)
        status, body = service.call('GET', '/v1/sources/law_unit:unit_d00d00000000000000000001')
        self.assertEqual(status, 200, body)
        loc = body['location']
        raw = fx['raw']
        first = raw.find(DUP_TEXT)
        self.assertGreater(loc['char_start'], first,
                           f'落在第一次出现处：char_start={loc["char_start"]} first={first}')
        self.assertEqual(loc['basis'], 'line_map')
        self.assertEqual(raw[loc['char_start']:loc['char_end']], DUP_TEXT)
        self.assertEqual(raw[:loc['char_start']].count('\n') + 1, 4)
        self.assertEqual(body['content']['text'], DUP_TEXT)

    def test_ambiguous_text_without_line_map_is_refused(self):
        # 行区间重拼不出单元正文（登记行是第 5 行"尾部"），退回全文查找时会碰到两处
        fx = build_duplicate_fixture(self.root, 5, 5)
        service = self._serve(fx)
        status, body = service.call('GET', '/v1/sources/law_unit:unit_d00d00000000000000000001')
        self.assertEqual(status, 409, f'多处命中却给出确定偏移：{status} {body}')
        self.assertEqual(body['code'], 'RANGE_INVALID')

    # -- 缺陷 5：库结构损坏被吞成 200 empty --------------------------------
    def test_corrupt_units_table_is_not_empty_result(self):
        fx = build_fixture(self.root)
        service = self._serve(fx)
        rw = sqlite3.connect(fx['db'])
        rw.execute('drop table units')
        rw.commit()
        rw.close()

        status, body = service.call('POST', '/v1/search', {'query': '违约金', 'kinds': ['law']})
        self.assertNotEqual((status, body.get('state')), (200, 'empty'),
                            f'库损坏被报成空结果：{status} {body}')
        self.assertEqual(status, 503, body)
        self.assertEqual(body['code'], 'SERVICE_DEGRADED')

        status, body = service.call('GET', '/v1/sources/law_unit:unit_000000000000000000000001')
        self.assertEqual(status, 503, body)
        self.assertEqual(body['code'], 'SERVICE_DEGRADED')

    def test_genuinely_absent_query_is_still_empty(self):
        # 反向保险：真没命中仍是 200 empty，别把"零命中"也升级成故障
        fx = build_fixture(self.root)
        service = self._serve(fx)
        status, body = service.call('POST', '/v1/search', {'query': '完全不存在的词条组合'})
        self.assertEqual(status, 200)
        self.assertEqual(body['state'], 'empty')
        self.assertEqual(body['degraded'], [])

    # -- 缺陷 3 残留：唯一文本回退时行号必须跟着真实偏移走 -----------------
    def test_unique_text_fallback_reports_actual_line(self):
        fx = build_misregistered_line_fixture(self.root)
        service = self._serve(fx)
        raw = fx['raw']
        status, body = service.call('GET', f'/v1/sources/law_unit:{MIS_UNIT_ID}')
        self.assertEqual(status, 200, body)
        loc = body['location']
        self.assertEqual(loc['basis'], 'text_search', '这个用例只可能靠唯一文本命中定位')
        self.assertEqual(loc['char_start'], len(MIS_LINES[0]) + 1)
        self.assertEqual(raw[loc['char_start']:loc['char_end']], MIS_TEXT)
        actual = raw.count('\n', 0, loc['char_start']) + 1
        self.assertEqual(actual, 2, '正文里这段文本就在第 2 行')
        # 登记的 3 是错的；行号必须按真实偏移给出，不能和 char_start 互相矛盾
        self.assertEqual(loc['line_start'], actual,
                         f'行号仍是登记值：line_start={loc["line_start"]} 实际={actual}')
        self.assertEqual(loc['line_end'], actual,
                         f'结束行仍是登记值：line_end={loc["line_end"]} 实际={actual}')

    def test_citation_line_matches_char_offset(self):
        # 同一条约束在检索路径上也成立：卡片上的行号来自这里
        fx = build_misregistered_line_fixture(self.root)
        service = self._serve(fx)
        status, body = service.call('POST', '/v1/search', {'query': MIS_TEXT, 'kinds': ['law']})
        self.assertEqual(status, 200, body)
        cites = body['groups']['law']
        self.assertTrue(cites, body)
        loc = cites[0]['location']
        actual = fx['raw'].count('\n', 0, loc['char_start']) + 1
        self.assertEqual(loc['basis'], 'text_search')
        self.assertEqual(loc['line_start'], actual,
                         f'检索引用的行号与偏移不一致：{loc["line_start"]} != {actual}')
        self.assertEqual(loc['line_end'], actual)

    def test_registered_line_map_still_uses_registered_lines(self):
        # 反向保险：登记行区间能重拼出正文时，行号仍应等于登记值，别被"重算"改坏
        fx = build_duplicate_fixture(self.root, 4, 4)
        service = self._serve(fx)
        status, body = service.call('GET', '/v1/sources/law_unit:unit_d00d00000000000000000001')
        self.assertEqual(status, 200, body)
        loc = body['location']
        self.assertEqual(loc['basis'], 'line_map')
        self.assertEqual((loc['line_start'], loc['line_end']), (4, 4))


if __name__ == '__main__':
    unittest.main(verbosity=2)
