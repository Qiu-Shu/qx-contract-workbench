"""Explicit, case-scoped derived memory; the local rows are always authoritative.

REST contract: Hindsight OpenAPI 1.1.0, inspected 2026-11-04 at
https://api.hindsight.vectorize.io/openapi.json. Adapter contract tested with a
local fake HTTP server, never with client case data or a cloud service.
"""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
import time
from urllib import error, parse, request
from uuid import uuid4

from business_store import CaseStore, encoded, stamp, window

NOTICE = '案件记忆是经选择保存的派生提示，不是证据；请核对来源原文。'
MAX_CONTENT = 16000
MAX_MEMORIES = 500
LEASE_SECONDS = 900


class MemoryConflict(ValueError):
    pass


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def bounded(value, label, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{label}须为 1–{maximum} 字。')
    return value


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('案件记忆服务不允许重定向。')


class HindsightAdapter:
    """Only an explicitly configured literal loopback service can receive data."""
    def __init__(self, url, token='', instance_id=''):
        parts = parse.urlsplit(url)
        try:
            loopback = ipaddress.ip_address(parts.hostname or '').is_loopback
            port = parts.port
        except ValueError:
            loopback, port = False, None
        if (parts.scheme not in ('http', 'https') or not loopback or
                parts.username or parts.password or parts.query or parts.fragment or
                parts.path not in ('', '/', '/engine') or not port):
            raise ValueError('记忆服务仅支持带端口的本机回环地址，不接受远程地址或网址凭据。')
        if not isinstance(token, str) or '\r' in token or '\n' in token:
            raise ValueError('记忆服务凭据格式无效。')
        self.url = url.rstrip('/')
        self.key = digest('instance:'+instance_id if instance_id else self.url)
        self.token = token
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect())

    def _request(self, method, bank, suffix='', payload=None):
        if bank is not None and not re.fullmatch(r'qx-[a-f0-9-]+', bank):
            raise ValueError('记忆库标识无效。')
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer '+self.token
        path = '/health/ready' if bank is None else '/v1/default/banks/'+bank+suffix
        req = request.Request(self.url+path,
                              data=encoded(payload).encode('utf-8') if payload is not None else None,
                              headers=headers, method=method)
        try:
            timeout = 5 if bank is None else 300 if method == 'POST' and suffix == '/memories' else 45
            with self.opener.open(req, timeout=timeout) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('记忆服务返回内容过大。')
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            if method == 'DELETE' and exc.code == 404:
                return {'success': True}
            raise RuntimeError('记忆服务请求失败。') from None

    def ready(self):
        self._request('GET', None)

    def retain(self, bank, memories):
        items = [{'content': m['content'], 'document_id': m['id']+'-r'+str(m['revision']),
                  'metadata': {'case_id': m['case_id'], 'source_sha256': m['source_sha256']},
                  'context': NOTICE} for m in memories]
        result = self._request('POST', bank, '/memories', {'items': items, 'async': False})
        if (result.get('success') is not True or result.get('async') is not False or
                result.get('bank_id') != bank or result.get('items_count') != len(items)):
            raise RuntimeError('记忆服务尚未确认全部索引完成。')

    def recall(self, bank, query):
        result = self._request('POST', bank, '/memories/recall',
                               {'query': query, 'types': ['world', 'experience'],
                                'budget': 'low', 'max_tokens': 3000})
        if not isinstance(result.get('results'), list):
            raise RuntimeError('记忆服务返回格式无效。')
        return result['results'][:100]

    def delete_bank(self, bank):
        result = self._request('DELETE', bank)
        if result.get('success') is not True:
            raise RuntimeError('记忆服务未确认删除。')


class CaseMemoryStore:
    def __init__(self, workspace, adapter=None):
        self.cases = CaseStore(workspace)
        self.adapter = adapter
        self.configuration_error = ''
        if adapter is None and os.environ.get('QX_HINDSIGHT_URL'):
            try:
                self.adapter = HindsightAdapter(os.environ['QX_HINDSIGHT_URL'],
                                                os.environ.get('QX_HINDSIGHT_TOKEN', ''),
                                                os.environ.get('QX_HINDSIGHT_INSTANCE_ID', ''))
            except ValueError:
                self.configuration_error = '记忆服务配置无效；仅允许本机回环地址。'
        with self.cases.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS case_memory_config(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), namespace TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS case_memory_state(
                    case_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
                    revision INTEGER NOT NULL DEFAULT 0, active_bank TEXT NOT NULL DEFAULT '',
                    synced_revision INTEGER NOT NULL DEFAULT -1, last_error TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS case_memories(
                    id TEXT PRIMARY KEY,case_id TEXT NOT NULL,content TEXT NOT NULL,
                    source TEXT NOT NULL,source_note_id TEXT NOT NULL,source_sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL,revision INTEGER NOT NULL,created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,source_stale INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS case_memory_case ON case_memories(case_id,created_at);
                CREATE TABLE IF NOT EXISTS case_memory_banks(
                    bank TEXT PRIMARY KEY,case_id TEXT NOT NULL,revision INTEGER NOT NULL,
                    endpoint_key TEXT NOT NULL,state TEXT NOT NULL,lease_until REAL NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            if not any(r['name'] == 'next_ordinal' for r in db.execute('PRAGMA table_info(case_memory_banks)')):
                db.execute('ALTER TABLE case_memory_banks ADD COLUMN next_ordinal INTEGER NOT NULL DEFAULT 0')
            db.execute('INSERT OR IGNORE INTO case_memory_config VALUES(1,?,1)', (str(uuid4()),))

    def _state(self, db, case_id):
        self.cases._case(db, case_id)
        db.execute('INSERT OR IGNORE INTO case_memory_state(case_id) VALUES(?)', (case_id,))
        stale = db.execute('''UPDATE case_memories SET source_stale=1 WHERE case_id=?
            AND source_stale=0 AND source_note_id!='' AND (NOT EXISTS(
            SELECT 1 FROM legal_notes n WHERE n.id=source_note_id AND n.case_id=case_memories.case_id)
            OR EXISTS(SELECT 1 FROM legal_notes n WHERE n.supersedes=source_note_id
            AND n.case_id=case_memories.case_id))''', (case_id,)).rowcount
        if stale:
            self._invalidate(db, case_id)
        return dict(db.execute('SELECT * FROM case_memory_state WHERE case_id=?', (case_id,)).fetchone())

    @staticmethod
    def _invalidate(db, case_id):
        db.execute("UPDATE case_memory_banks SET state='retired' WHERE case_id=? AND state IN ('active','staging')", (case_id,))
        db.execute("UPDATE case_memory_state SET revision=revision+1,active_bank='',last_error='' WHERE case_id=?", (case_id,))

    def _enabled(self, db, state):
        return bool(state['enabled'] and db.execute('SELECT enabled FROM case_memory_config').fetchone()[0])

    def _status(self, db, case_id=None):
        config = db.execute('SELECT * FROM case_memory_config').fetchone()
        result = {'case_id': case_id, 'global_enabled': bool(config['enabled']),
                  'enabled': bool(config['enabled']), 'case_enabled': True,
                  'service_configured': self.adapter is not None, 'sync_state': 'pending' if self.adapter else 'unconfigured',
                  'pending_cleanup': 0, 'revision': 0, 'last_error': self.configuration_error,
                  'notice': NOTICE}
        if case_id is not None:
            state = self._state(db, case_id)
            banks = db.execute('SELECT * FROM case_memory_banks WHERE case_id=?', (case_id,)).fetchall()
            enabled = self._enabled(db, state)
            current = any(b['bank'] == state['active_bank'] and b['state'] == 'active' and
                          self.adapter and b['endpoint_key'] == self.adapter.key for b in banks)
            result.update(case_enabled=bool(state['enabled']), enabled=enabled, revision=state['revision'],
                          last_error=state['last_error'] or self.configuration_error,
                          pending_cleanup=sum(b['state'] in ('retired', 'uncertain') or (b['state'] == 'building' and b['lease_until'] <= time.time()) or b['revision'] != state['revision'] or b['endpoint_key'] != getattr(self.adapter, 'key', '') for b in banks))
            result['sync_state'] = ('disabled' if not enabled else 'unconfigured' if not self.adapter else
                'syncing' if any(b['state'] == 'building' and b['lease_until'] > time.time() for b in banks) else
                'error' if state['last_error'] else 'ready' if current and state['synced_revision'] == state['revision'] else 'pending')
            result['memory_count'] = db.execute('SELECT COUNT(*) FROM case_memories WHERE case_id=?', (case_id,)).fetchone()[0]
            if enabled and self.adapter and result['memory_count'] == 0:
                result['sync_state'] = 'empty'
        elif not result['enabled']:
            result['sync_state'] = 'disabled'
        return result

    def status(self, case_id=None):
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._status(db, case_id)

    def list_cases(self, query='', offset=0, limit=20):
        return self.cases.list(query, offset, min(int(limit), 50))

    @staticmethod
    def _memory(row, db=None):
        result = dict(row)
        result['source'] = json.loads(result['source'])
        result['source_stale'] = bool(result['source_stale'])
        result['source_changed'] = result['source_stale']
        result['source_warning'] = '来源笔记已被更正；此记忆不再参与检索，请重新选择当前笔记。' if result['source_stale'] else ''
        result['current_source_note_ids'] = [result['source_note_id']] if result['source_note_id'] and not result['source_stale'] else []
        if db is not None and result['source_stale']:
            result['current_source_note_ids'] = [r[0] for r in db.execute(
                '''WITH RECURSIVE corrections(id) AS (SELECT id FROM legal_notes WHERE id=? AND case_id=? UNION
                SELECT n.id FROM legal_notes n JOIN corrections c ON n.supersedes=c.id WHERE n.case_id=?)
                SELECT id FROM corrections c WHERE NOT EXISTS(SELECT 1 FROM legal_notes n
                WHERE n.supersedes=c.id AND n.case_id=?) LIMIT 50''',
                (result['source_note_id'], result['case_id'], result['case_id'], result['case_id']))]
        result['notice'] = NOTICE
        return result

    def _row(self, db, case_id, memory_id):
        self._state(db, case_id)
        row = db.execute('SELECT * FROM case_memories WHERE case_id=? AND id=?', (case_id, memory_id)).fetchone()
        if row is None:
            raise ValueError('本案件不存在这条记忆。')
        return row

    @staticmethod
    def _knowledge_query(terms=()):
        # Deduplicate before pagination/top-k; separate sources and manual records stay distinct.
        match = ' AND ('+' OR '.join('instr(casefold(content),?)>0' for _ in terms)+')' if terms else ''
        return '''WITH ranked AS (SELECT id,ROW_NUMBER() OVER (
            PARTITION BY CASE WHEN source_note_id='' THEN id ELSE '' END,
            source_note_id,revision,source_sha256,content ORDER BY created_at,id) AS occurrence
            FROM case_memories WHERE case_id=? AND source_stale=0'''+match+''')
            SELECT * FROM case_memories WHERE id IN (SELECT id FROM ranked WHERE occurrence=1)'''

    def list(self, case_id, offset=0, limit=20, require_enabled=False, deduplicate=False):
        offset, limit = window(offset, limit, 50)
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._state(db, case_id)
            if require_enabled and not self._enabled(db, state):
                return {'enabled': False, 'memories': [], 'message': '案件记忆已关闭。'}
            query = self._knowledge_query() if deduplicate else 'SELECT * FROM case_memories WHERE case_id=?'
            total = db.execute('SELECT COUNT(*) FROM ('+query+')', (case_id,)).fetchone()[0]
            rows = db.execute(query+' ORDER BY created_at,id LIMIT ? OFFSET ?', (case_id, limit, offset))
            return {'case_id': case_id, 'memories': [self._memory(r, db) for r in rows], 'total': total,
                    'offset': offset, 'next_offset': offset+limit if offset+limit < total else None, 'notice': NOTICE}

    def read(self, case_id, memory_id, require_enabled=False):
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._state(db, case_id)
            if require_enabled and not self._enabled(db, state):
                return {'enabled': False, 'message': '案件记忆已关闭。'}
            return self._memory(self._row(db, case_id, memory_id), db)

    def sources(self, case_id, offset=0, limit=20):
        offset, limit = window(offset, limit, 50)
        with self.cases.db() as db:
            self.cases._case(db, case_id)
            where = '''case_id=? AND length(content) BETWEEN 1 AND ? AND NOT EXISTS(
                SELECT 1 FROM legal_notes newer WHERE newer.case_id=n.case_id AND newer.supersedes=n.id)'''
            total = db.execute('SELECT COUNT(*) FROM legal_notes n WHERE '+where, (case_id, MAX_CONTENT)).fetchone()[0]
            rows = db.execute('SELECT id,case_id,kind,content,source,created_at FROM legal_notes n WHERE '+where+
                              ' ORDER BY created_at,id LIMIT ? OFFSET ?', (case_id, MAX_CONTENT, limit, offset))
            return {'case_id': case_id, 'notes': [{**dict(r), 'content_chars': len(r['content']), 'eligible': True} for r in rows],
                    'total': total, 'offset': offset, 'next_offset': offset+limit if offset+limit < total else None}

    def add(self, case_id, note_id=None, content=None, source=None, confirmed=False):
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._state(db, case_id)
            if not self._enabled(db, state):
                raise ValueError('案件记忆已关闭，请先启用。')
            if db.execute('SELECT COUNT(*) FROM case_memories WHERE case_id=?', (case_id,)).fetchone()[0] >= MAX_MEMORIES:
                raise ValueError('本案记忆已达 500 条，请先整理现有内容。')
            if note_id:
                if content is not None or source is not None:
                    raise ValueError('选中笔记的内容与来源必须由系统读取，不能覆盖。')
                row = db.execute('SELECT * FROM legal_notes WHERE case_id=? AND id=?', (case_id, note_id)).fetchone()
                if row is None or db.execute('SELECT 1 FROM legal_notes WHERE case_id=? AND supersedes=?', (case_id, note_id)).fetchone():
                    raise ValueError('请选择本案件未被更正的笔记。')
                content = bounded(row['content'], '笔记正文', MAX_CONTENT)
                source_value = {'label': row['source'], 'snapshot': content, 'note_id': note_id,
                                'kind': row['kind'], 'case_id': case_id, 'created_at': row['created_at'],
                                'citations': json.loads(row['citations'])}
                kind = 'selected_note'
            else:
                if confirmed is not True:
                    raise ValueError('手工记忆需要明确确认内容与来源。')
                content = bounded(content, '记忆正文', MAX_CONTENT)
                source_value = {'label': bounded(source, '来源说明', 1000), 'snapshot': content,
                                'note_id': '', 'kind': 'manual', 'case_id': case_id, 'created_at': stamp(), 'citations': []}
                kind = 'manual'
            source_hash = digest(encoded(source_value))
            if len(encoded(source_value)) > 32000:
                raise ValueError('笔记来源信息过长，请选择更精简且带来源的笔记。')
            source_value['sha256'] = source_hash
            identifier, now = str(uuid4()), stamp()
            db.execute('INSERT INTO case_memories VALUES(?,?,?,?,?,?,?,?,?,?,0)',
                       (identifier, case_id, content, encoded(source_value), note_id or '', source_hash, kind, 1, now, now))
            self._invalidate(db, case_id)
            return {'memory': self._memory(self._row(db, case_id, identifier)), **self._status(db, case_id)}

    @staticmethod
    def _revision(row, revision):
        if type(revision) is not int or revision != row['revision']:
            raise MemoryConflict('记忆已被修改，请刷新后再操作。')

    def update(self, case_id, memory_id, revision, content, require_current=False):
        content = bounded(content, '记忆正文', MAX_CONTENT)
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._row(db, case_id, memory_id)
            self._revision(row, revision)
            if require_current:
                if not self._enabled(db, self._state(db, case_id)):
                    raise MemoryConflict('案件记忆已关闭，请刷新后重试。')
                if row['source_stale']:
                    raise MemoryConflict('记忆来源已变化，请重新核对。')
            db.execute('UPDATE case_memories SET content=?,revision=revision+1,updated_at=? WHERE case_id=? AND id=?',
                       (content, stamp(), case_id, memory_id))
            self._invalidate(db, case_id)
            return {'memory': self._memory(self._row(db, case_id, memory_id)), **self._status(db, case_id)}

    def delete(self, case_id, memory_id, revision):
        with self.cases.db() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            self._revision(self._row(db, case_id, memory_id), revision)
            db.execute('DELETE FROM case_memories WHERE case_id=? AND id=?', (case_id, memory_id))
            self._invalidate(db, case_id)
            return {'id': memory_id, 'deleted': True, **self._status(db, case_id)}

    def settings(self, enabled, case_id=None):
        if type(enabled) is not bool:
            raise ValueError('启用状态必须为布尔值。')
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if case_id is not None:
                self._state(db, case_id)
                db.execute('UPDATE case_memory_state SET enabled=? WHERE case_id=?', (int(enabled), case_id))
                self._invalidate(db, case_id)
            else:
                db.execute('UPDATE case_memory_config SET enabled=?', (int(enabled),))
                for row in db.execute('SELECT case_id FROM case_memory_state').fetchall():
                    self._invalidate(db, row['case_id'])
            return self._status(db, case_id)

    def recall(self, case_id, query, limit=10, use_hindsight=True, deduplicate=False):
        query = bounded(query, '检索词', 1000)
        _, limit = window(0, limit, 30)
        remote, mode = [], 'local_fallback'
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            status = self._status(db, case_id)
            state = self._state(db, case_id)
            if deduplicate and status['enabled']:
                db.create_function('casefold', 1, str.casefold)
                terms = query.casefold().split()
                rows = db.execute(self._knowledge_query(terms)+' ORDER BY created_at,id LIMIT ?',
                                  (case_id, *terms, limit+1)).fetchall()
                return {**status, 'matches': [self._memory(row) for row in rows[:limit]],
                        'has_more': len(rows) > limit, 'mode': 'local_fallback', 'query': query,
                        'retrieval_notice': '本机关键词匹配；相同来源的重复记录只返回一次。'}
        if not status['enabled']:
            return {**status, 'matches': [], 'mode': 'disabled'}
        if use_hindsight is True and status['sync_state'] == 'ready' and status['memory_count']:
            try:
                remote = self.adapter.recall(state['active_bank'], query)
                mode = 'hindsight'
            except Exception:
                mode = 'local_fallback'
                with self.cases.db() as db:
                    db.execute('UPDATE case_memory_state SET last_error=? WHERE case_id=? AND active_bank=? AND revision=?',
                               ('增强检索暂不可用，将从本机记忆重建索引。', case_id, state['active_bank'], state['revision']))
        # Recheck the generation after network I/O; never return remote prose.
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._state(db, case_id)
            status = self._status(db, case_id)
            if not status['enabled']:
                return {**status, 'matches': [], 'mode': 'disabled'}
            rows = db.execute('SELECT * FROM case_memories WHERE case_id=? AND source_stale=0 ORDER BY created_at,id', (case_id,)).fetchall()
            mapped = {r['id']+'-r'+str(r['revision']): r for r in rows}
            matches, seen = [], set()
            if current['revision'] != state['revision'] or current['active_bank'] != state['active_bank']:
                remote, mode = [], 'local_fallback'
            for hit in remote:
                row = mapped.get(hit.get('document_id')) if isinstance(hit, dict) else None
                if row is not None and row['id'] not in seen:
                    matches.append(self._memory(row));seen.add(row['id'])
            if not matches:
                mode = 'local_fallback'
                terms = query.casefold().split()
                matches = [self._memory(row) for row in rows if any(term in row['content'].casefold() for term in terms)]
            return {**status, 'matches': matches[:limit], 'mode': mode,
                    'has_more': len(matches) > limit, 'query': query,
                    'retrieval_notice': 'Hindsight 语义排序，返回本案当前保存的原文。' if mode == 'hindsight' else '本机关键词匹配；本次未使用 Hindsight 语义结果。'}

    def _cleanup(self, case_id):
        if self.adapter is None:
            return
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._state(db, case_id)
            db.execute("UPDATE case_memory_banks SET state='uncertain' WHERE case_id=? AND state='building' AND lease_until<?", (case_id, time.time()))
            banks = db.execute("SELECT bank,state FROM case_memory_banks WHERE case_id=? AND state IN ('retired','uncertain') AND endpoint_key=? AND (state='retired' OR lease_until<?) ORDER BY (state='retired') DESC,lease_until,bank LIMIT 1", (case_id, self.adapter.key, time.time())).fetchall()
        for row in banks:
            try:
                self.adapter.delete_bank(row['bank'])
            except Exception:
                continue
            with self.cases.db() as db:
                db.execute("DELETE FROM case_memory_banks WHERE case_id=? AND bank=? AND state='retired'", (case_id, row['bank']))
                # A timed-out retain might still recreate the bank: keep its id,
                # retry deletion every five minutes, and report cleanup pending.
                db.execute("UPDATE case_memory_banks SET lease_until=? WHERE case_id=? AND bank=? AND state='uncertain'", (time.time()+300, case_id, row['bank']))

    def sync(self, case_id):
        status = self.status(case_id)
        if self.adapter is None:
            return status
        if status['memory_count'] == 0 and not status['pending_cleanup']:
            return status
        self._cleanup(case_id)
        if not status['enabled'] or status['memory_count'] == 0:
            return self.status(case_id)
        try:
            self.adapter.ready()
        except Exception:
            with self.cases.db() as db:
                db.execute('UPDATE case_memory_state SET last_error=? WHERE case_id=?', ('记忆服务尚未就绪；本机内容已保存，待重试。', case_id))
            return self.status(case_id)
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._state(db, case_id)
            if not self._enabled(db, state):
                return self._status(db, case_id)
            if db.execute("SELECT 1 FROM case_memory_banks WHERE case_id=? AND state='building' AND lease_until>?", (case_id, time.time())).fetchone():
                return self._status(db, case_id)
            if self._status(db, case_id)['sync_state'] == 'ready':
                return self._status(db, case_id)
            rows = [dict(r) for r in db.execute('SELECT * FROM case_memories WHERE case_id=? AND source_stale=0 ORDER BY id', (case_id,))]
            staged = db.execute("SELECT * FROM case_memory_banks WHERE case_id=? AND revision=? AND endpoint_key=? AND state='staging' LIMIT 1", (case_id, state['revision'], self.adapter.key)).fetchone()
            if staged:
                bank, cursor = staged['bank'], staged['next_ordinal']
                db.execute("UPDATE case_memory_banks SET state='building',lease_until=? WHERE bank=?", (time.time()+LEASE_SECONDS, bank))
            else:
                namespace = db.execute('SELECT namespace FROM case_memory_config').fetchone()[0]
                bank, cursor = 'qx-'+namespace+'-'+uuid4().hex, 0
                db.execute('INSERT INTO case_memory_banks VALUES(?,?,?,?,?,?,0)',
                           (bank, case_id, state['revision'], self.adapter.key, 'building', time.time()+LEASE_SECONDS))
            batch = rows[cursor:cursor+5]
        failed = False
        try:
            if batch:
                self.adapter.retain(bank, batch)
        except Exception:
            failed = True
        with self.cases.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._state(db, case_id)
            building = db.execute("SELECT 1 FROM case_memory_banks WHERE bank=? AND state='building' AND lease_until>?", (bank, time.time())).fetchone()
            if not failed and building and current['revision'] == state['revision'] and self._enabled(db, current):
                if cursor+len(batch) < len(rows):
                    db.execute("UPDATE case_memory_banks SET state='staging',next_ordinal=? WHERE bank=?", (cursor+len(batch), bank))
                    db.execute("UPDATE case_memory_state SET last_error='' WHERE case_id=?", (case_id,))
                else:
                    db.execute("UPDATE case_memory_banks SET state='retired' WHERE case_id=? AND state='active'", (case_id,))
                    db.execute("UPDATE case_memory_banks SET state='active' WHERE bank=?", (bank,))
                    db.execute("UPDATE case_memory_state SET active_bank=?,synced_revision=?,last_error='' WHERE case_id=?", (bank, state['revision'], case_id))
            else:
                db.execute('UPDATE case_memory_banks SET state=?,lease_until=0 WHERE bank=?', ('uncertain' if failed else 'retired', bank))
                if failed:
                    db.execute('UPDATE case_memory_state SET last_error=? WHERE case_id=?', ('记忆服务暂不可用；本机修改已保存，待重试。', case_id))
        return self.status(case_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True)
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(100001)
        if len(raw) > 100000:
            raise ValueError('记忆请求过大。')
        value = json.loads(raw)
        allowed = {'status', 'list_cases', 'list', 'read', 'sources', 'add', 'update', 'delete', 'settings', 'recall', 'sync'}
        if value.get('action') not in allowed or not isinstance(value.get('args', {}), dict):
            raise ValueError('不支持的案件记忆操作。')
        result = getattr(CaseMemoryStore(args.workspace), value['action'])(**value.get('args', {}))
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else '案件记忆操作未完成，请检查参数或本机服务。'
        print(json.dumps({'ok': False, 'error': message, 'status': 409 if isinstance(exc, MemoryConflict) else 400}, ensure_ascii=False))
