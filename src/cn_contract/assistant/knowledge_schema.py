"""assistant-knowledge-v1: widen the receipt handler set for the read-only knowledge service.

为什么必须改表
--------------
`assistant_handler_receipts.handler_id` 上有一个 CHECK，只允许
`legal_library.search` / `legal_library.read_original`。把只读知识服务接进同一条
显式检索路径后，回执要如实记下"这次是 `legal_knowledge.search` 跑的"；
要么加宽这个 CHECK，要么就得在回执里写一个假的 handler 名——后者会让审计记录说谎，
也让"这条引用从哪来"无法回查。

SQLite 不能原地改 CHECK，所以按既有做法重建一次：建新表 → 导数据 → 删旧表 →
改名 → 重建两个不可变触发器。其余对象的字节保持不变。

重建期间 `assistant_library_citations` 仍以 `receipt_id` 引用被删的父表，
所以这套语句必须在 `PRAGMA foreign_keys=OFF` 的窗口里执行（见
`REQUIRES_FOREIGN_KEYS_OFF`）。
"""
import sqlite3

from . import library_schema

# 升级器需要为这个版本打开 FK OFF 窗口。
REQUIRES_FOREIGN_KEYS_OFF = True

TABLES = library_schema.TABLES

_COLUMNS = ('id', 'run_id', 'event_seq', 'handler_id', 'handler_version', 'payload_sha256',
            'request_json', 'result_json', 'result_sha256', 'scope_json', 'created_at')
_INSERT_COLUMNS = ','.join(_COLUMNS)

# 除 handler_id 的取值集合外，与 v1 的建表语句逐字一致。
_WIDENED = library_schema.STATEMENTS[0].replace(
    "CHECK(handler_id IN ('legal_library.search','legal_library.read_original'))",
    "CHECK(handler_id IN ('legal_library.search','legal_library.read_original','legal_knowledge.search'))")
assert _WIDENED != library_schema.STATEMENTS[0], 'handler_id CHECK 未找到，迁移会变成空操作'

STATEMENTS = (
    '''CREATE TABLE assistant_handler_receipts_knowledge (
        id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL REFERENCES assistant_runs(id),
        event_seq INTEGER NOT NULL CHECK(event_seq > 0),
        handler_id TEXT NOT NULL CHECK(handler_id IN ('legal_library.search','legal_library.read_original','legal_knowledge.search')),
        handler_version TEXT NOT NULL CHECK(handler_version = '1'),
        payload_sha256 TEXT NOT NULL,
        request_json TEXT NOT NULL CHECK(length(request_json) <= 8192),
        result_json TEXT NOT NULL CHECK(length(result_json) <= 262144),
        result_sha256 TEXT NOT NULL,
        scope_json TEXT NOT NULL CHECK(length(scope_json) <= 4096),
        created_at TEXT NOT NULL,
        UNIQUE(run_id,event_seq,handler_id,handler_version),
        FOREIGN KEY(run_id,event_seq) REFERENCES assistant_run_events(run_id,seq))''',
    f'INSERT INTO assistant_handler_receipts_knowledge ({_INSERT_COLUMNS}) '
    f'SELECT {_INSERT_COLUMNS} FROM assistant_handler_receipts',
    'DROP TABLE assistant_handler_receipts',
    'ALTER TABLE assistant_handler_receipts_knowledge RENAME TO assistant_handler_receipts',
    "CREATE TRIGGER immutable_assistant_handler_receipts_update BEFORE UPDATE ON "
    "assistant_handler_receipts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_assistant_handler_receipts_delete BEFORE DELETE ON "
    "assistant_handler_receipts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
)


def _select(db):
    return [tuple(row) for row in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN "
        "('assistant_handler_receipts','assistant_library_citations') ORDER BY type,name")]


def expected_objects():
    """迁移之后的精确对象行：由 v1 建表语句 + 本模块重建语句确定性推导。"""
    with sqlite3.connect(':memory:') as db:
        for statement in library_schema.STATEMENTS + STATEMENTS:
            db.execute(statement)
        return _select(db)


def _found(raw):
    return [tuple(row) for row in raw.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN "
        "('assistant_handler_receipts','assistant_library_citations') ORDER BY type,name")]


def initialize_storage(database):
    """把全新工作区里刚建好的 v1 回执表就地加宽。

    只处理"表刚建、还没有引用行"的情形：带历史数据的库走版本化迁移
    （有备份、有 FK OFF 窗口、有前后哈希核对），不在这里就地改。
    """
    raw = database.engine.raw_connection()
    try:
        found = _found(raw)
        if not found or found == expected_objects():
            return
        if found != list(library_schema.expected_objects()):
            return
        if raw.execute('SELECT COUNT(*) FROM assistant_library_citations').fetchone()[0]:
            return
        for statement in STATEMENTS:
            raw.execute(statement)
        raw.commit()
        if _found(raw) != expected_objects():
            raise ValueError('DATABASE_SCHEMA_MISMATCH')
    finally:
        raw.close()
