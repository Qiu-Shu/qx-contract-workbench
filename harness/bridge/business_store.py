"""Explicit case membership and append-only notes over the existing material database."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from store import MaterialStore


def stamp():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def window(offset, limit, maximum=100):
    return max(0, int(offset)), max(1, min(int(limit), maximum))


class CaseStore(MaterialStore):
    def __init__(self, workspace):
        supplied = workspace if isinstance(workspace, MaterialStore) else None
        super().__init__(supplied.root if supplied is not None else workspace)
        self.store = supplied if supplied is not None else MaterialStore(self.root)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS legal_cases(
                    id TEXT PRIMARY KEY,title TEXT NOT NULL,our_role TEXT NOT NULL,
                    created_at TEXT NOT NULL,request_id TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS legal_material_links(
                    link_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,path TEXT NOT NULL,
                    version INTEGER NOT NULL,sha256 TEXT NOT NULL,bytes INTEGER NOT NULL,
                    mtime INTEGER NOT NULL,linked_at TEXT NOT NULL,UNIQUE(case_id,path,version));
                CREATE TABLE IF NOT EXISTS legal_notes(
                    id TEXT PRIMARY KEY,case_id TEXT NOT NULL,kind TEXT NOT NULL,content TEXT NOT NULL,
                    source TEXT NOT NULL,supersedes TEXT NOT NULL,citations TEXT NOT NULL,
                    warnings TEXT NOT NULL,verification TEXT NOT NULL,created_at TEXT NOT NULL,
                    request_id TEXT,request_json TEXT NOT NULL,UNIQUE(case_id,request_id));
                CREATE INDEX IF NOT EXISTS legal_note_case ON legal_notes(case_id,created_at);
                CREATE INDEX IF NOT EXISTS legal_note_correction ON legal_notes(supersedes);
                CREATE TABLE IF NOT EXISTS legal_receptions(
                    id TEXT PRIMARY KEY,case_id TEXT NOT NULL,client_note_id TEXT NOT NULL,
                    internal_note_id TEXT NOT NULL,request_id TEXT,request_json TEXT NOT NULL,
                    UNIQUE(case_id,request_id));
                CREATE TABLE IF NOT EXISTS legal_material_snapshots(
                    link_id TEXT PRIMARY KEY,status TEXT NOT NULL,warnings TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS legal_material_chunks(
                    link_id TEXT NOT NULL,ordinal INTEGER NOT NULL,page INTEGER,
                    location TEXT NOT NULL,text TEXT NOT NULL,PRIMARY KEY(link_id,ordinal));
            ''')

    @staticmethod
    def _case(db, case_id):
        row = db.execute('SELECT * FROM legal_cases WHERE id=?', (case_id,)).fetchone()
        if row is None:
            raise ValueError('案件不存在，请使用明确的案件编号。')
        return dict(row)

    def create(self, title, our_role='', request_id=''):
        if not isinstance(title, str) or not title.strip():
            raise ValueError('请填写案件名称。')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if request_id:
                old = db.execute('SELECT * FROM legal_cases WHERE request_id=?', (request_id,)).fetchone()
                if old:
                    if (old['title'], old['our_role']) != (title, our_role):
                        raise ValueError('同一请求编号不能创建不同案件。')
                    return dict(old)
            identifier = str(uuid4())
            db.execute('INSERT INTO legal_cases VALUES(?,?,?,?,?)',
                       (identifier, title, our_role, stamp(), request_id or None))
            return self._case(db, identifier)

    def list(self, query='', offset=0, limit=20):
        offset, limit = window(offset, limit)
        with self.db() as db:
            where = ' WHERE instr(title,?)>0' if query else ''
            args = (query,) if query else ()
            total = db.execute('SELECT COUNT(*) FROM legal_cases'+where, args).fetchone()[0]
            rows = db.execute('SELECT * FROM legal_cases'+where+' ORDER BY created_at,id LIMIT ? OFFSET ?', (*args, limit, offset))
            return {'cases': [dict(r) for r in rows], 'total': total,
                    'next_offset': offset+limit if offset+limit < total else None}

    def link_materials(self, case_id, paths):
        with self.db() as db:
            self._case(db, case_id)
        # Registration streams the original hash; no files are copied or rewritten.
        registered = [self.store.register(path) for path in dict.fromkeys(paths)]
        linked = []
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._case(db, case_id)
            for material in registered:
                old = db.execute('SELECT * FROM legal_material_links WHERE case_id=? AND path=? ORDER BY version DESC LIMIT 1',
                                 (case_id, material['path'])).fetchone()
                if old and old['sha256'] == material['sha256']:
                    self._capture_material(db, old)
                    linked.append(dict(old));continue
                row = {'link_id': str(uuid4()), 'case_id': case_id, 'path': material['path'],
                       'version': old['version']+1 if old else 1, 'sha256': material['sha256'],
                       'bytes': material['size'], 'mtime': material['mtime'], 'linked_at': stamp()}
                db.execute('INSERT INTO legal_material_links VALUES(:link_id,:case_id,:path,:version,:sha256,:bytes,:mtime,:linked_at)', row)
                self._capture_material(db, row)
                linked.append(row)
        return {'case_id': case_id, 'materials': linked}

    def _capture_material(self, db, link):
        material = db.execute('SELECT * FROM materials WHERE path=? AND sha256=?',
                              (link['path'], link['sha256'])).fetchone()
        if material is None or material['status'] not in ('ready', 'partial'):
            return
        db.execute('INSERT OR IGNORE INTO legal_material_snapshots VALUES(?,?,?)',
                   (link['link_id'], material['status'], material['warnings']))
        # Parsing may add pages later; already archived text is never replaced.
        db.execute('INSERT OR IGNORE INTO legal_material_chunks SELECT ?,ordinal,page,location,text FROM chunks WHERE path=?',
                   (link['link_id'], link['path']))
        if material['status'] == 'ready':
            db.execute("UPDATE legal_material_snapshots SET status='ready' WHERE link_id=?", (link['link_id'],))

    def _linked(self, db, case_id, path, version=None):
        self._case(db, case_id)
        key = self.safe(path, must_exist=False).relative_to(self.root).as_posix()
        condition = '' if version is None else ' AND version=?'
        args = (case_id, key) if version is None else (case_id, key, version)
        row = db.execute('SELECT * FROM legal_material_links WHERE case_id=? AND path=?'+condition+' ORDER BY version DESC LIMIT 1', args).fetchone()
        if row is None:
            raise ValueError('该材料尚未关联此案件，请先明确关联；不能读取或引用其他案件材料。')
        return dict(row)

    def _material_status(self, row):
        value = dict(row);value.update(changed=False, missing=False, current_sha256=None, warnings=[])
        try:
            source = self.safe(row['path'])
            before = source.stat()
            with source.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                value['changed'] = True;value['warnings'].append('文件正在变化，请保存完成后重新读取。')
            value['current_sha256'] = digest
            if digest != row['sha256']:
                value['changed'] = True;value['warnings'].append('原文件已变化；旧关联和笔记保留，请重新关联当前版本后解析。')
        except (OSError, ValueError):
            value['missing'] = True;value['warnings'].append('原文件已丢失或当前路径不可读取；历史关联仍保留。')
        return value

    def _materials(self, db, case_id, include_history=False):
        self._case(db, case_id)
        condition = '' if include_history else ' AND version=(SELECT MAX(b.version) FROM legal_material_links b WHERE b.case_id=a.case_id AND b.path=a.path)'
        rows = db.execute('SELECT * FROM legal_material_links a WHERE case_id=?'+condition+' ORDER BY path,version', (case_id,)).fetchall()
        return [self._material_status(row) for row in rows]

    def materials(self, case_id, include_history=False):
        with self.db() as db:
            return self._materials(db, case_id, include_history)

    def _citations(self, db, case_id, citations):
        self._case(db, case_id)
        results, warnings = [], []
        if citations is not None and not isinstance(citations, (list, tuple)):
            citations = [citations]
        for index, citation in enumerate(citations or [], 1):
            if not isinstance(citation, dict):
                results.append({'provided': citation, 'status': 'unverified'})
                warnings.append(f'引文{index}缺少来源位置，已保留待核。');continue
            if citation.get('case_id', case_id) != case_id:
                raise ValueError('引文不能引用其他案件编号。')
            item = dict(citation);issues = []
            if not isinstance(item.get('path'), str) or not item['path'].strip():
                item['status'] = 'unverified';results.append(item)
                warnings.append(f'引文{index}缺少材料路径，已保留待核。');continue
            link = self._linked(db, case_id, item['path'])
            expected = item.get('sha256', link['sha256'])
            if isinstance(expected, str) and expected != link['sha256']:
                historical = db.execute('SELECT * FROM legal_material_links WHERE case_id=? AND path=? AND sha256=? ORDER BY version DESC LIMIT 1',
                                        (case_id, link['path'], expected)).fetchone()
                if historical is not None:
                    link = dict(historical)
            current = self._material_status(link)
            item.update(path=link['path'], link_id=link['link_id'], version=link['version'])
            item['sha256'] = expected
            if expected != link['sha256'] or current['changed'] or current['missing']:
                issues.append('来源版本已变化或不可读取')
            material = db.execute('SELECT * FROM materials WHERE path=?', (link['path'],)).fetchone()
            if not material or material['sha256'] != link['sha256'] or material['status'] not in ('ready', 'partial'):
                issues.append('该版本尚未解析')
            quote = item.get('quote', item.get('exact_quote'))
            rows = db.execute('SELECT ordinal,text FROM chunks WHERE path=? ORDER BY ordinal', (link['path'],))
            matched = False
            for chunk in rows:
                if item.get('chunk') is not None and item['chunk'] != chunk['ordinal']:
                    continue
                text = chunk['text']
                if isinstance(quote, str) and quote:
                    if 'start' in item or 'end' in item:
                        start, end = item.get('start'), item.get('end')
                        matched = type(start) is int and type(end) is int and 0 <= start < end <= len(text) and text[start:end] == quote
                    else:
                        matched = quote in text
                if matched:
                    item['chunk'] = chunk['ordinal'];break
            if not matched:
                issues.append('逐字引文或片段位置未匹配')
            item['status'] = 'unverified' if issues else 'matched'
            results.append(item)
            warnings.extend(f'引文{index}：{reason}，正文已保留待核。' for reason in issues)
        return results, warnings

    def validate_citations(self, case_id, citations):
        with self.db() as db:
            values, warnings = self._citations(db, case_id, citations)
            return {'citations': values, 'warnings': warnings}

    @staticmethod
    def _note(row, start=0, limit=4000):
        value = dict(row)
        for field in ('citations', 'warnings'):
            value[field] = json.loads(value[field])
        value.pop('request_json', None)
        content = value['content'];value['content'] = content[start:start+limit]
        value.update(content_chars=len(content), start=start,
                     next_start=start+limit if start+limit < len(content) else None,
                     review_status='unverified')
        return value

    def add_note(self, case_id, kind, content, source='', supersedes='', citations=None, request_id=''):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._add_note(db, case_id, kind, content, source, supersedes, citations, request_id)

    def _add_note(self, db, case_id, kind, content, source='', supersedes='', citations=None, request_id=''):
        if not isinstance(content, str) or not isinstance(kind, str) or not kind.strip():
            raise ValueError('请提供笔记类别及文字正文。')
        request = encoded({'kind': kind, 'content': content, 'source': source,
                           'supersedes': supersedes, 'citations': citations or []})
        self._case(db, case_id)
        if request_id:
            old = db.execute('SELECT * FROM legal_notes WHERE case_id=? AND request_id=?', (case_id, request_id)).fetchone()
            if old:
                if old['request_json'] != request:
                    raise ValueError('同一请求编号不能保存不同正文。')
                return self._note(old)
        if supersedes:
            old = db.execute('SELECT * FROM legal_notes WHERE id=?', (supersedes,)).fetchone()
            if old is None or old['case_id'] != case_id:
                raise ValueError('只能更正本案件已有笔记，不能跨案关联。')
            tips = db.execute('WITH RECURSIVE chain(id) AS (SELECT ? UNION ALL '
                'SELECT n.id FROM legal_notes n JOIN chain ON n.supersedes=chain.id WHERE n.case_id=?) '
                'SELECT id FROM chain WHERE NOT EXISTS(SELECT 1 FROM legal_notes n WHERE n.supersedes=chain.id AND n.case_id=?)',
                (supersedes, case_id, case_id)).fetchall()
            current_ids = [row['id'] for row in tips]
            if old['kind'] != kind or current_ids != [supersedes]:
                return {'recorded': False, 'case_id': case_id, 'current_note_ids': current_ids,
                        'reason': 'correction_kind_mismatch' if old['kind'] != kind else 'correction_conflict',
                        'message': '更正须沿用原类别，客户回复和内部底稿分别新增。' if old['kind'] != kind else '原记录已有更正，请回读当前记录后再续接更正。',
                        'unsaved_note': {**json.loads(request), 'request_id': request_id}}
        values, warnings = self._citations(db, case_id, citations)
        identifier = str(uuid4())
        db.execute('INSERT INTO legal_notes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   (identifier, case_id, kind, content, source, supersedes, encoded(values), encoded(warnings),
                    'matched' if values and not warnings else 'unverified', stamp(), request_id or None, request))
        return self._note(db.execute('SELECT * FROM legal_notes WHERE id=?', (identifier,)).fetchone())

    def record_reception(self, case_id, client_reply, internal_note, source='', request_id=''):
        if not isinstance(client_reply, str) or not isinstance(internal_note, str):
            raise ValueError('客户回复和内部底稿请分别提供自然语言正文。')
        request = encoded(dict(client_reply=client_reply, internal_note=internal_note, source=source))
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._case(db, case_id)
            old = db.execute('SELECT * FROM legal_receptions WHERE case_id=? AND request_id=?',
                             (case_id, request_id or None)).fetchone()
            if old:
                if old['request_json'] != request:
                    raise ValueError('同一请求编号不能保存不同接待正文。')
                client = self._note(db.execute('SELECT * FROM legal_notes WHERE id=?', (old['client_note_id'],)).fetchone())
                internal = self._note(db.execute('SELECT * FROM legal_notes WHERE id=?', (old['internal_note_id'],)).fetchone())
                identifier = old['id']
            else:
                client = self._add_note(db, case_id, 'client_reply', client_reply, source)
                internal = self._add_note(db, case_id, 'internal_note', internal_note, source)
                identifier = str(uuid4())
                db.execute('INSERT INTO legal_receptions VALUES(?,?,?,?,?,?)',
                           (identifier, case_id, client['id'], internal['id'], request_id or None, request))
            return {'recorded': True, 'reception_id': identifier, 'case_id': case_id,
                    'client_reply': client, 'internal_note': internal}

    def get(self, case_id, offset=0, limit=30, include_history=False):
        offset, limit = window(offset, limit)
        with self.db() as db:
            db.execute('BEGIN')
            case = self._case(db, case_id)
            condition = '' if include_history else ' AND NOT EXISTS(SELECT 1 FROM legal_notes newer WHERE newer.case_id=n.case_id AND newer.supersedes=n.id)'
            total = db.execute('SELECT COUNT(*) FROM legal_notes n WHERE case_id=?'+condition, (case_id,)).fetchone()[0]
            rows = db.execute('SELECT * FROM legal_notes n WHERE case_id=?'+condition+' ORDER BY created_at,id LIMIT ? OFFSET ?', (case_id, limit, offset))
            notes = [self._note(row) for row in rows]
            materials = self._materials(db, case_id, include_history)
        return {'case': case, 'notes': notes, 'total_notes': total, 'include_history': include_history,
                'next_offset': offset+limit if offset+limit < total else None,
                'materials': materials}

    def export_snapshot(self, case_id):
        with self.db() as db:
            db.execute('BEGIN')
            case = self._case(db, case_id)
            rows = db.execute('SELECT * FROM legal_notes n WHERE case_id=? AND NOT EXISTS('
                'SELECT 1 FROM legal_notes newer WHERE newer.case_id=n.case_id AND newer.supersedes=n.id) '
                'ORDER BY created_at,id', (case_id,)).fetchall()
            return {'case': case, 'notes': [self._note(row, limit=len(row['content'])) for row in rows],
                    'materials': self._materials(db, case_id)}

    def read_note(self, case_id, note_id, start=0, limit=8000):
        start, limit = window(start, limit, 16000)
        with self.db() as db:
            self._case(db, case_id)
            row = db.execute('SELECT * FROM legal_notes WHERE case_id=? AND id=?', (case_id, note_id)).fetchone()
            if row is None:
                raise ValueError('本案件不存在这条笔记。')
            return self._note(row, start, limit)

    def read_material(self, case_id, path, start=0, limit=6, page=None, version=None):
        start, limit = window(start, limit, 12)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            link = self._linked(db, case_id, path, version)
            self._capture_material(db, link)
            snapshot = db.execute('SELECT * FROM legal_material_snapshots WHERE link_id=?', (link['link_id'],)).fetchone()
            condition = 'link_id=?' + (' AND page=?' if page is not None else '')
            args = (link['link_id'],) if page is None else (link['link_id'], page)
            total = db.execute('SELECT COUNT(*) FROM legal_material_chunks WHERE '+condition, args).fetchone()[0]
            rows = db.execute('SELECT ordinal,page,location,text FROM legal_material_chunks WHERE '+condition+
                              ' ORDER BY ordinal LIMIT ? OFFSET ?', (*args, limit, start)).fetchall()
        status = self._material_status(link)
        if version is not None and snapshot is not None:
            return {'case_id': case_id, 'path': link['path'], 'sha256': link['sha256'],
                    'material_version': link['version'], 'historical_snapshot': True,
                    'status': snapshot['status'], 'total_chunks': total, 'chunks': [dict(row) for row in rows],
                    'next_start': start+len(rows) if start+len(rows) < total else None,
                    'warnings': [*json.loads(snapshot['warnings']), '返回登记版本的解析文字快照，不代表原始二进制文件仍存在。'], 'material': status}
        if status['changed'] or status['missing']:
            return {'case_id': case_id, 'path': link['path'], 'chunks': [], 'next_start': None,
                    'warnings': status['warnings'] + (['该版本没有已保存的解析文字快照。'] if version is not None else []), 'material': status}
        result = self.store.read(link['path'], start, limit, page)
        status = self._material_status(link)
        if result['sha256'] != link['sha256'] or status['changed'] or status['missing']:
            return {'case_id': case_id, 'path': link['path'], 'chunks': [], 'next_start': None,
                    'warnings': status['warnings'] or ['读取期间材料版本变化，请重新关联和读取。'], 'material': status}
        return {'case_id': case_id, 'material_version': link['version'], **result}

    def search(self, case_id, query, offset=0, limit=10):
        if not query.strip():
            raise ValueError('请输入检索词。')
        offset, limit = window(offset, limit, 30)
        materials = self.materials(case_id)
        allowed = {m['path']: m for m in materials if not m['changed'] and not m['missing']}
        warnings = [warning for m in materials for warning in m['warnings']]
        matches = []
        with self.db() as db:
            notes = db.execute('SELECT id,kind,content FROM legal_notes n WHERE case_id=? AND instr(content,?)>0 AND NOT EXISTS(SELECT 1 FROM legal_notes newer WHERE newer.case_id=n.case_id AND newer.supersedes=n.id) ORDER BY created_at,id', (case_id, query))
            for row in notes:
                left = max(0, row['content'].find(query)-120)
                matches.append({'kind': 'note', 'note_id': row['id'], 'note_kind': row['kind'], 'excerpt': row['content'][left:left+600]})
                if len(matches) > offset+limit:break
        if len(matches) <= offset+limit:
            for path in sorted(allowed):
                page_offset = 0
                while True:
                    try:found = self.store.search(query, path=path, offset=page_offset, limit=30)
                    except ValueError:break
                    status = self._material_status(allowed[path])
                    if status['changed'] or status['missing']:
                        matches = [item for item in matches if item.get('path') != path]
                        warnings.extend(status['warnings'])
                        break
                    matches.extend({'kind': 'material', **m} for m in found['matches'])
                    if len(matches) > offset+limit or found['next_offset'] is None:break
                    page_offset = found['next_offset']
                if len(matches) > offset+limit:break
        return {'case_id': case_id, 'query': query, 'matches': matches[offset:offset+limit],
                'next_offset': offset+limit if len(matches) > offset+limit else None,
                'warnings': list(dict.fromkeys(warnings))}
