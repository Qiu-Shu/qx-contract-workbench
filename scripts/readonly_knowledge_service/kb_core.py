"""只读知识服务的数据层：法条（SQLite 只读）与案例（Markdown 原文锚点）。

设计约束（来自试点任务书，代码里逐条对应）
--------------------------------------------
1. **只读**：SQLite 一律 `mode=ro` + `PRAGMA query_only=ON`；路径不存在时直接报错，
   绝不 `connect()` 出一个空库。所有 SQL 都是常量字符串 + 参数绑定，不拼接用户输入。
2. **引用回到原文**：法条摘自 `documents.raw_text`，案例摘自 24 册原始 Markdown；
   检索用的 `corpus.jsonl` 只用来"定位是哪一案"，它的字符偏移不参与截原文。
3. **先校验再返回**：来源不存在、原文哈希与登记值不符、范围越界都明确阻断，不补造引用。
4. **不伪造覆盖**：数量、命中数都从文件/库现算，不写死常量。

本模块只用标准库，任何 Python 3.12+ 都能直接跑。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------- 常量与错误

MAX_QUERY_CHARS = 200
MAX_SNIPPET_CHARS = 300
MAX_SOURCE_CHARS = 20000
MAX_LIMIT = 10

LAW_ID = re.compile(r'unit_[0-9a-f]{24}')
CASE_ID = re.compile(r'\d{4}年度案例【[^】]{1,40}】#\d{3}')
LAW_PREFIX = 'law_unit:'
CASE_PREFIX = 'case_book:'


class ServiceFault(Exception):
    """带稳定错误码的业务失败；HTTP 层按 code 映射状态码。"""

    def __init__(self, code: str, message: str):
        super().__init__(code)
        self.code = code
        self.message = message

    @property
    def status(self) -> int:
        return {
            'BAD_REQUEST': 400,
            'UNAUTHORIZED': 401,
            'SOURCE_NOT_FOUND': 404,
            'SOURCE_STALE': 409,
            'RANGE_INVALID': 409,
            'QUERY_INVALID': 422,
            'SERVICE_DEGRADED': 503,
        }.get(self.code, 400)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def normalize(text: str) -> str:
    """检索前归一：全角转半角在调用方已做，这里只压缩空白。"""
    return re.sub(r'\s+', ' ', text).strip()


_SPLIT = re.compile(r'[\s,，。、；;：:？?！!（）()《》〈〉"“”\'’\[\]【】]+')


def split_segments(query: str) -> list[str]:
    """把查询切成"必须同时出现"的几段。

    空格是用户表达 AND 的唯一手段，所以这里按空格与标点切段；
    单字段落信息量太低又会把 `LIKE` 拖成全表扫描，因此优先保留 ≥2 字的段，
    整句都是单字时才退化成原文。结果去重且保序，便于把实际用的段写进响应。
    """
    parts = [part.strip() for part in _SPLIT.split(query) if part and part.strip()]
    segments = [part for part in parts if len(part) >= 2]
    if not segments:
        cleaned = normalize(query)
        segments = [cleaned] if cleaned else []
    return list(dict.fromkeys(segments))


# ---------------------------------------------------------------- BM25（案例）

class CaseIndex:
    """案例检索：对清洗语料做 BM25，但引用一律回原文。

    不做倒排索引——1,581 案逐案扫 `str.count` 只要几毫秒，
    换来的是启动零延迟、内存只放正文，且不会出现"索引与原文脱节"。
    """

    K1 = 1.2
    B = 0.75

    def __init__(self, corpus_path: Path, cases_path: Path, case_root: Path):
        self.corpus_path = corpus_path
        self.cases_path = cases_path
        self.case_root = case_root
        self.docs: list[dict] = []
        self.anchors: dict[str, dict] = {}
        self.avg_len = 0.0
        self._volume_text: dict[str, tuple[str, str]] = {}
        self._volume_stat: dict[str, tuple[int, int]] = {}
        self._load()

    def _load(self) -> None:
        with self.cases_path.open(encoding='utf-8') as handle:
            for line in handle:
                row = json.loads(line)
                self.anchors[row['case_id']] = row
        with self.corpus_path.open(encoding='utf-8') as handle:
            for line in handle:
                row = json.loads(line)
                text = normalize(row.get('text') or '')
                if not text:
                    continue
                title = (row.get('title') or '').lstrip('# ').strip()
                self.docs.append({'case_id': row['case_id'], 'title': title,
                                  'cause': row.get('cause') or '', 'text': text,
                                  'len': len(text)})
        self.avg_len = (sum(doc['len'] for doc in self.docs) / len(self.docs)) if self.docs else 0.0

    # -- 原始 Markdown 读取（带哈希校验与缓存） -----------------------------
    def volume_text(self, md_rel: str) -> str:
        cached = self._volume_text.get(md_rel)
        path = self.case_root / md_rel
        if not path.exists():
            raise ServiceFault('SOURCE_NOT_FOUND', f'案例原文不存在：{Path(md_rel).name}')
        stat = path.stat()
        stamp = (stat.st_size, stat.st_mtime_ns)
        if cached is not None and self._volume_stat.get(md_rel) == stamp:
            return cached[0]
        text = path.read_text(encoding='utf-8')
        self._volume_text[md_rel] = (text, _sha256_file(path))
        self._volume_stat[md_rel] = stamp
        return text

    def volume_sha(self, md_rel: str) -> str:
        self.volume_text(md_rel)
        return self._volume_text[md_rel][1]

    # -- 检索 ---------------------------------------------------------------
    @staticmethod
    def _terms(query: str) -> list[str]:
        """中文按字符二元组、英文数字按整词；两字中文词天然就是一个二元组。"""
        terms: list[str] = []
        for chunk in re.findall(r'[\u4e00-\u9fff]+|[A-Za-z0-9]+', query):
            if re.fullmatch(r'[A-Za-z0-9]+', chunk):
                terms.append(chunk.lower())
                continue
            if len(chunk) == 1:
                terms.append(chunk)
            else:
                terms.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
        return list(dict.fromkeys(terms))

    def search(self, query: str, limit: int) -> list[dict]:
        """案例检索：先按"每段都必须出现"筛候选，再用字符二元组 BM25 排序。

        纯 BM25 在中文短查询上不可用——几个高频二元组就能把无关案例顶上来。
        法律检索的直觉是"我写的几段都要沾上"，所以先用子串做 AND 过滤（精确、可解释），
        再在候选里算 BM25 决定先后；一段都凑不齐时放宽到"过半段落"，并把这个让步
        记在返回的 `relaxed` 上，不假装是完整匹配。
        """
        segments = [segment.lower() for segment in split_segments(query)]
        if not segments:
            return []
        candidates, relaxed = self._filter(segments)
        if not candidates:
            return []
        terms = self._terms(' '.join(segments))
        total = max(len(self.docs), 1)
        df = {term: 0 for term in terms}
        for doc in candidates:
            for term in terms:
                if term in doc['text'].lower():
                    df[term] += 1
        idf = {term: math.log(1 + (total - count + 0.5) / (count + 0.5))
               for term, count in df.items()}
        scored = []
        for doc in candidates:
            haystack = doc['text'].lower()
            norm = 1 - self.B + self.B * doc['len'] / (self.avg_len or 1)
            score = 0.0
            for term in terms:
                value = haystack.count(term)
                if value:
                    score += idf[term] * value * (self.K1 + 1) / (value + self.K1 * norm)
            scored.append({'case_id': doc['case_id'], 'score': round(score, 6),
                           'relaxed': relaxed, 'matched_segments': len(segments) if not relaxed else None})
        scored.sort(key=lambda item: (-item['score'], item['case_id']))
        return scored[:limit]

    def _filter(self, segments: list[str]) -> tuple[list[dict], bool]:
        full = [doc for doc in self.docs
                if all(segment in doc['text'].lower() for segment in segments)]
        if full or len(segments) == 1:
            return full, False
        need = (len(segments) + 1) // 2
        loose = [doc for doc in self.docs
                 if sum(1 for segment in segments if segment in doc['text'].lower()) >= need]
        return loose, True

    # -- 引用定位 -----------------------------------------------------------
    def cite(self, case_id: str, query: str) -> dict:
        anchor = self.anchors.get(case_id)
        if anchor is None:
            raise ServiceFault('SOURCE_NOT_FOUND', '案例不在已登记清单内')
        md_rel = anchor['anchor']['md_rel']
        text = self.volume_text(md_rel)
        registered = anchor['anchor']['md_sha256']
        actual = self.volume_sha(md_rel)
        if registered != actual:
            raise ServiceFault('SOURCE_STALE', '案例原文哈希与登记值不符，已阻断引用')
        start = anchor['anchor']['char_start']
        end = anchor['anchor']['char_end']
        if not 0 <= start < end <= len(text):
            raise ServiceFault('RANGE_INVALID', '案例锚点超出原文长度')
        block = text[start:end]
        if not block.strip():
            raise ServiceFault('RANGE_INVALID', '案例锚点落在空白区域')
        return {'text': text, 'block': block, 'block_start': start, 'block_end': end,
                'md_rel': md_rel, 'sha256': actual,
                'line_start': anchor['anchor']['line_start'],
                'line_end': anchor['anchor']['line_end']}

    def case_meta(self, case_id: str) -> dict:
        row = self.anchors[case_id]
        return {'case_id': case_id, 'volume': row['volume'], 'title': row['title'],
                'cause': row.get('cause') or '', 'case_no': row.get('case_no') or '',
                'court': row.get('court') or '', 'doc_type': row.get('doc_type') or ''}


# ---------------------------------------------------------------- 法条

@dataclass
class LawHit:
    unit_id: str
    doc_id: str
    label: str
    kind: str
    start_line: int
    end_line: int
    heading_path: str
    text: str
    doc_title: str
    doc_sha: str
    score: float


class LawIndex:
    """法条检索：走既有的 `units_fts`（trigram）。

    注意 trigram 分词器要求 ≥3 个字符，两字查询（如"定金"）会**静默 0 命中**。
    所以短查询与 FTS 无结果时退回 `LIKE`，并把实际用的通道写进结果，
    免得把"分词器限制"伪装成"库里没有"。
    """

    def __init__(self, db_path: Path):
        if not db_path.exists():
            raise ServiceFault('SOURCE_NOT_FOUND', f'法条库不存在：{db_path.name}')
        self.db_path = db_path
        self.uri = f'file:{db_path}?mode=ro'
        try:
            with self._connect() as conn:
                self.documents = conn.execute('select count(*) from documents').fetchone()[0]
                self.units = conn.execute('select count(*) from units').fetchone()[0]
        except sqlite3.Error as error:
            # 结构和 IO 层面的失败必须在启动时就说清楚，不能带着半个库上线，
            # 更不能等到查询时才表现成"库里没有"。
            raise ServiceFault('SERVICE_DEGRADED',
                               f'法条库结构不可用：{type(error).__name__}') from None

    def _connect(self) -> sqlite3.Connection:
        # immutable=0：仍然走文件锁；mode=ro 由 SQLite 强制，写语句会直接抛错。
        conn = sqlite3.connect(self.uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        return conn

    def _bounded(self, sql: str, params: tuple, budget_ms: int) -> tuple[list[sqlite3.Row], bool]:
        """跑一条可能很慢的查询，超预算就由 SQLite 自己中断。

        不能只"跑完再判断有没有超时"——`LIKE '%词%'` 在 80 万行上没有索引可用，
        单条语句就是几秒，事后判断只能承认超时，没法止损。这里用 progress handler
        每 2000 个 VM 步检查一次，超预算直接中断，把控制权拿回来。
        """
        conn = self._connect()
        deadline = time.monotonic() + budget_ms / 1000.0
        aborted = {'value': False}

        def progress() -> int:
            if time.monotonic() > deadline:
                aborted['value'] = True
                return 1
            return 0

        conn.set_progress_handler(progress, 2000)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as error:
            # 只有"预算到点被自己中断"才算部分结果；其余 OperationalError 是库结构
            # 或 IO 出了真问题，必须往上抛。过去这里一律 rows=[]，于是"units 表被删"
            # 会安静地返回 200 empty，和"这个词库里确实没有"长得一模一样。
            if not aborted['value']:
                raise ServiceFault('SERVICE_DEGRADED',
                                   f'法条库查询失败：{type(error).__name__}') from None
            rows = []
        finally:
            conn.set_progress_handler(None, 0)
            conn.close()
        return rows, aborted['value']

    def readonly_probe(self) -> dict:
        """自证只读：尝试写 `meta` 必须失败。失败才是只读的证据。"""
        try:
            with self._connect() as conn:
                conn.execute("insert into meta(key,value) values('pilot_probe','x')")
            return {'write_blocked': False}
        except sqlite3.Error as error:
            return {'write_blocked': True, 'error': type(error).__name__}

    def search(self, query: str, limit: int) -> tuple[list[dict], str, bool]:
        """返回 (命中, 实际通道, 是否因预算不足而中断)。

        多词查询按"每一段都必须出现"处理（AND 语义），与法律检索的直觉一致：
        用空格分开的几段是并列的必要条件，不是可选项。trigram 分词器要求 ≥3 字符，
        短词走 `LIKE` 并带时间预算；被中断时 `partial=True`，不假装扫完了全库。
        """
        segments = split_segments(query)
        if not segments:
            return [], 'none', False
        if all(len(segment) >= 3 for segment in segments):
            rows = self._fts(segments, limit)
            if rows:
                return rows, 'fts5_trigram_and', False
        rows, partial = self._like(segments, limit)
        return rows, 'like_bounded', partial

    def _row_to_hit(self, row: sqlite3.Row) -> dict:
        rank = row['rank'] if 'rank' in row.keys() else None
        return {'unit_id': row['id'], 'doc_id': row['doc_id'], 'label': row['label'],
                'kind': row['kind'], 'start_line': row['start_line'], 'end_line': row['end_line'],
                'heading_path': row['heading_path'], 'text': row['text'],
                'doc_title': row['title'], 'doc_sha': row['sha256'],
                'score': float(-rank) if rank is not None else 0.0}

    def _fts(self, segments: list[str], limit: int) -> list[dict]:
        # 每段加双引号当短语，段间 AND；用户输入里的 FTS 语法字符因此不会被当成操作符。
        match = ' AND '.join('"' + segment.replace('"', '""') + '"' for segment in segments)
        sql = ('select u.id,u.doc_id,u.label,u.kind,u.start_line,u.end_line,u.heading_path,u.text,'
               'd.title,d.sha256,bm25(units_fts) as rank '
               'from units_fts f join units u on u.rowid=f.rowid join documents d on d.id=u.doc_id '
               'where units_fts match ? order by rank limit ?')
        try:
            with self._connect() as conn:
                return [self._row_to_hit(row) for row in conn.execute(sql, (match, limit))]
        except sqlite3.Error as error:
            # 索引不可用同样是故障，不是"0 命中"；宁可 503，也不给一个假的空结果。
            raise ServiceFault('SERVICE_DEGRADED',
                               f'法条索引查询失败：{type(error).__name__}') from None

    def _like(self, segments: list[str], limit: int, budget_ms: int = 1500) -> tuple[list[dict], bool]:
        """短词/混合词：用最长的一段在 SQL 层过滤，其余段落回 Python 里再筛。"""
        escaped = segments[0].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        sql = ('select u.id,u.doc_id,u.label,u.kind,u.start_line,u.end_line,u.heading_path,u.text,'
               'd.title,d.sha256,null as rank '
               'from units u join documents d on d.id=u.doc_id '
               "where u.text like ? escape '\\' limit ?")
        rows, aborted = self._bounded(sql, (f'%{escaped}%', limit * 40), budget_ms)
        hits = []
        for row in rows:
            hit = self._row_to_hit(row)
            body = hit['text']
            if all(segment in body for segment in segments):
                hits.append(hit)
            if len(hits) >= limit:
                break
        return hits[:limit], aborted

    def unit_by_id(self, unit_id: str) -> dict:
        """取单元 + 原文，并**当场重算**原文哈希。

        `documents.sha256` 是登记值，不是"当前文件的指纹"。只把登记值当结论返回，
        等于假设原文永远不会被改——改过之后引用照样标着"校验通过"。
        所以这里重算一遍，与登记值不符就阻断；返回值里的 `doc_sha` 一律是重算值。
        """
        sql = ('select u.id,u.doc_id,u.label,u.kind,u.start_line,u.end_line,u.heading_path,u.text,'
               'd.title,d.sha256,d.raw_text from units u join documents d on d.id=u.doc_id '
               'where u.id=?')
        try:
            with self._connect() as conn:
                row = conn.execute(sql, (unit_id,)).fetchone()
        except sqlite3.Error as error:
            raise ServiceFault('SERVICE_DEGRADED',
                               f'法条库读取失败：{type(error).__name__}') from None
        if row is None:
            raise ServiceFault('SOURCE_NOT_FOUND', '法条片段不在库内')
        hit = self._row_to_hit(row)
        raw = row['raw_text']
        hit['raw_text'] = raw
        actual = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        if actual != hit['doc_sha']:
            raise ServiceFault('SOURCE_STALE', '原文哈希与 documents.sha256 登记值不符，已阻断引用')
        hit['doc_sha'] = actual
        return hit

    @staticmethod
    def locate(hit: dict) -> tuple[int, int, str, int, int]:
        """把单元文本映射回 `raw_text` 的字符区间。

        `units.start_line/end_line` 是 1-based 闭区间，所以偏移可以直接由"前几行的
        长度加换行"累加得到。**不能用 `raw.find(候选)`**：同一部法里重复条文很常见，
        `find` 只会返回第一次出现的位置，于是第 40 行的条文被标成第 3 行的偏移，
        而校验（片段 == units.text）照样通过——错得很安静。

        行区间重拼出来的片段与原单元文本不一致时，退回全文查找，但**只在唯一命中时**
        才给出偏移；多处命中说明定位本身没有依据，宁可拒绝也不猜。

        返回值是 `(char_start, char_end, basis, line_start, line_end)`。行号**一律由
        最终采用的字符偏移反算**，不再回传 `units` 里的登记值：文本回退一旦把位置
        挪到别处，登记行号就不再描述这段字符，两者同时输出会互相矛盾——卡片写
        "第 3 行"，偏移却落在第 2 行。`basis` 会写明是靠登记行区间（line_map）还是
        靠唯一文本命中（text_search）定位的，调用方不必自己判断。
        """
        raw = hit['raw_text']
        lines = raw.split('\n')
        begin, end = hit['start_line'] - 1, hit['end_line']
        if 0 <= begin < end <= len(lines):
            candidate = '\n'.join(lines[begin:end])
            offset = sum(len(line) + 1 for line in lines[:begin])
            if (raw[offset:offset + len(candidate)] == candidate
                    and candidate.strip() == hit['text'].strip()):
                return offset, offset + len(candidate), 'line_map', begin + 1, end
        needle = hit['text'].strip()
        if not needle:
            raise ServiceFault('RANGE_INVALID', '法条片段为空')
        occurrences = []
        cursor = raw.find(needle)
        while cursor >= 0:
            occurrences.append(cursor)
            cursor = raw.find(needle, cursor + 1)
        if not occurrences:
            raise ServiceFault('RANGE_INVALID', '法条片段在原文中定位失败')
        if len(occurrences) > 1:
            raise ServiceFault(
                'RANGE_INVALID',
                f'法条片段在原文中出现 {len(occurrences)} 次，且登记行区间重拼不一致，'
                '无法确定唯一位置，已拒绝给出带偏移的引用')
        offset = occurrences[0]
        end = offset + len(needle)
        # 登记行号在这里已经不可信（它指向的位置放不下这段文本），按真实偏移反算。
        return offset, end, 'text_search', raw.count('\n', 0, offset) + 1, raw.count('\n', 0, end - 1) + 1


# ---------------------------------------------------------------- 片段工具

def snippet_around(text: str, start: int, end: int, query: str, limit: int = MAX_SNIPPET_CHARS) -> dict:
    """在原文里定位查询词，取定长窗口；找不到就把窗口放在块首并如实标注。"""
    terms = [t for t in CaseIndex._terms(query)]
    lower_text = text.lower()
    best = None
    for term in terms:
        position = lower_text.find(term, start, end)
        if position >= 0 and (best is None or position < best[0]):
            best = (position, term)
    if best is None:
        window_end = min(len(text), start + limit)
        return {'start': start, 'end': window_end, 'text': text[start:window_end],
                'match_start': None, 'match_end': None, 'match_field': 'block'}
    match_start, term = best
    match_end = match_start + len(term)
    left = max(start, match_start - limit // 3)
    window_end = min(end, left + limit) if end > left else min(len(text), left + limit)
    if window_end - left < limit // 2:
        left = max(start, window_end - limit)
    return {'start': left, 'end': window_end, 'text': text[left:window_end],
            'match_start': match_start, 'match_end': match_end, 'match_field': 'body'}


def clip(text: str, start: int, end: int, limit: int = MAX_SOURCE_CHARS) -> dict:
    if not 0 <= start < end <= len(text):
        raise ServiceFault('RANGE_INVALID', '请求范围超出原文长度')
    stop = min(end, start + limit)
    return {'start': start, 'end': stop, 'text': text[start:stop], 'truncated': stop < end,
            'full_length': len(text)}
