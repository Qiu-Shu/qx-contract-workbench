"""Opt-in local document library; original files and citation versions are retained."""
import argparse
from datetime import datetime, timezone
import hashlib
from itertools import chain
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import os
from uuid import UUID

from store import MaterialStore


def now():
    return datetime.now(timezone.utc).isoformat()


def chunk_digest(chunk):
    value=json.dumps([chunk['page'],chunk['location'],chunk['text']],ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]


def citation_for(identifier, digest, chunk):
    return f"KB:{identifier}:{chunk['ordinal']}:{digest[:12]}:{chunk_digest(chunk)}"


class KnowledgeStore:
    def __init__(self, workspace):
        outer = MaterialStore(workspace)
        directory = outer.safe(outer.root / 'knowledge', internal=True, must_exist=False)
        directory.mkdir(exist_ok=True)
        self.store = MaterialStore(directory)
        with self.store.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS kb_documents(
                id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                category TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', error TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0)''')
            # Only the opt-in library gets a full-text index, not the case workspace.
            try:
                new_fts = not db.execute("SELECT 1 FROM sqlite_master WHERE name='kb_fts'").fetchone()
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(text, tokenize='trigram')")
                db.executescript('''
                    CREATE TRIGGER IF NOT EXISTS kb_chunks_insert AFTER INSERT ON chunks BEGIN
                      INSERT INTO kb_fts(rowid,text) VALUES(new.rowid,new.text); END;
                    CREATE TRIGGER IF NOT EXISTS kb_chunks_delete AFTER DELETE ON chunks BEGIN
                      DELETE FROM kb_fts WHERE rowid=old.rowid; END;
                    CREATE TRIGGER IF NOT EXISTS kb_chunks_update AFTER UPDATE ON chunks BEGIN
                      DELETE FROM kb_fts WHERE rowid=old.rowid;
                      INSERT INTO kb_fts(rowid,text) VALUES(new.rowid,new.text); END;
                ''')
                db.execute('CREATE TABLE IF NOT EXISTS kb_migrations(name TEXT PRIMARY KEY)')
                if new_fts or not db.execute("SELECT 1 FROM kb_migrations WHERE name='fts-backfill-v1'").fetchone():
                    db.execute('''INSERT INTO kb_fts(rowid,text) SELECT c.rowid,c.text FROM chunks c
                        LEFT JOIN kb_fts f ON f.rowid=c.rowid WHERE f.rowid IS NULL''')
                    db.execute("INSERT OR IGNORE INTO kb_migrations VALUES('fts-backfill-v1')")
                self.fts = True
            except sqlite3.OperationalError as error:
                if not any(term in str(error) for term in ('no such module', 'no such tokenizer')):
                    raise
                self.fts = False

    def _document(self, db, document_id, *, allow_archived=False):
        row = db.execute('SELECT * FROM kb_documents WHERE id=?', (str(document_id),)).fetchone()
        if row is None:
            raise ValueError('未找到这份知识库资料。')
        if row['archived'] and not allow_archived:
            raise ValueError('这份资料已归档，不再用于检索或引用。')
        return row

    def _current(self, db, document):
        source, _, material = self.store.current(document['path'], db)
        if material['sha256'] != document['sha256']:
            raise ValueError('资料版本已变化，请重新上传为新版本。')
        return source, material

    def register(self, document_id, title, category='未分类'):
        identifier = str(UUID(document_id))
        title = str(title).strip()
        category = str(category).strip() or '未分类'
        if not title or len(title) > 240 or len(category) > 80:
            raise ValueError('资料名称须为 1–240 字，分类不超过 80 字。')
        directory = self.store.safe(self.store.root / 'documents' / identifier, internal=True)
        files = [p for p in directory.iterdir() if p.is_file()]
        if len(files) != 1:
            raise ValueError('上传文件不完整，请重新上传。')
        material = self.store.register(files[0])
        with self.store.db() as db:
            previous = db.execute('SELECT * FROM kb_documents WHERE id=?', (identifier,)).fetchone()
            if previous:
                if previous['sha256'] != material['sha256']:
                    raise ValueError('上传标识已存在，不能覆盖旧版本。')
                return dict(previous)
            duplicate = db.execute('SELECT id,title FROM kb_documents WHERE sha256=? AND archived=0', (material['sha256'],)).fetchone()
            db.execute('INSERT INTO kb_documents(id,path,title,category,sha256,created_at) VALUES(?,?,?,?,?,?)',
                       (identifier, material['path'], title, category, material['sha256'], now()))
        return {'id': identifier, 'title': title, 'state': 'pending',
                'duplicate_of': dict(duplicate) if duplicate else None}

    def list(self, offset=0, limit=50, archived=False):
        offset = max(0, int(offset)); limit = max(1, min(int(limit), 100))
        with self.store.db() as db:
            total = db.execute('SELECT count(*) FROM kb_documents WHERE archived=?', (int(archived),)).fetchone()[0]
            rows = db.execute('''SELECT d.*,m.size AS bytes,m.page_count,m.warnings,
                (SELECT count(*) FROM chunks c WHERE c.path=d.path) AS chunks
                FROM kb_documents d JOIN materials m ON m.path=d.path WHERE d.archived=?
                ORDER BY d.created_at DESC,d.id LIMIT ? OFFSET ?''', (int(archived), limit, offset)).fetchall()
        documents = [dict(row) for row in rows]
        for row in documents:
            row['warnings'] = json.loads(row['warnings'])
        return {'documents': documents, 'total': total, 'offset': offset,
                'next_offset': offset+len(rows) if offset+len(rows) < total else None,
                'search_mode': '全文检索' if self.fts else '原文匹配'}

    def set_state(self, document_id, state, error=''):
        if state not in {'pending','indexing','partial','ready','no_text','error'}:
            raise ValueError('无效的处理状态。')
        with self.store.db() as db:
            self._document(db, document_id, allow_archived=True)
            db.execute('UPDATE kb_documents SET state=?,error=? WHERE id=?', (state, str(error)[:500], document_id))

    def index(self, document_id):
        with self.store.db() as db:
            document = dict(self._document(db, document_id))
            self._current(db, document)
        self.set_state(document_id, 'indexing')
        try:
            page = 1
            while page is not None:
                with self.store.db() as db:
                    self._document(db, document_id)
                request = {'workspace': str(self.store.root), 'path': document['path'], 'start_page': page, 'page_count': 20}
                process = subprocess.run([sys.executable, str(Path(__file__).with_name('reader.py'))],
                    input=json.dumps(request), capture_output=True, text=True, encoding='utf-8',
                    timeout=600, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                if process.returncode:
                    raise ValueError('文档解析未完成，原件已保留，可稍后重新解析。')
                try:
                    result = json.loads(process.stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    raise ValueError('文档解析返回异常，原件已保留。') from None
                if not result.get('ok'):
                    raise ValueError(result.get('error', '解析失败'))
                result = result['result']
                page = result.get('next_page')
            self.set_state(document_id, result['status'])
            return {'id': document_id, **result}
        except Exception as error:
            message = str(error) if isinstance(error, ValueError) else '解析中断或超时，原件已保留，请稍后重试。'
            self.set_state(document_id, 'error', message)
            raise ValueError(message) from None

    def search(self, query, category='', offset=0, limit=12):
        query = str(query).strip()
        if not query or len(query) > 300:
            raise ValueError('请输入 1–300 字的检索词；多个关键词用空格分隔。')
        terms = list(dict.fromkeys(query.split()))[:12]
        offset = max(0, int(offset)); limit = max(1, min(int(limit), 30))
        params = []
        filters = ["d.archived=0", "d.state IN ('ready','partial')"]
        if category:
            filters.append('d.category=?'); params.append(category)
        base = ' FROM chunks c JOIN kb_documents d ON d.path=c.path JOIN materials m ON m.path=c.path '
        if self.fts and all(len(term) >= 3 for term in terms):
            match = ' OR '.join('"'+term.replace('"','""')+'"' for term in terms)
            base += ' JOIN kb_fts ON kb_fts.rowid=c.rowid '
            filters.append('kb_fts MATCH ?'); params.append(match)
            ordering = 'bm25(kb_fts),d.created_at DESC,d.id,c.ordinal'
        else:
            filters.append('('+' OR '.join('instr(lower(c.text),lower(?))>0' for _ in terms)+')')
            params.extend(terms)
            ordering = 'd.created_at DESC,d.id,c.ordinal'
        with self.store.db() as db:
            rows = db.execute('SELECT c.*,d.id,d.title,d.sha256,d.category,d.created_at,m.size,m.mtime'+base+
                ' WHERE '+' AND '.join(filters)+' ORDER BY '+ordering, params)
            # Inspect only short edges for terms split at the reader's chunk boundary.
            boundary = db.execute('''WITH edges AS (
                SELECT path,ordinal,substr(text,-299) AS tail,
                    lead(ordinal) OVER w AS next_ordinal,lead(substr(text,1,299)) OVER w AS head
                FROM chunks WINDOW w AS (PARTITION BY path ORDER BY ordinal))
                SELECT c.*,d.id,d.title,d.sha256,d.category,d.created_at,e.next_ordinal,
                    e.tail || e.head AS boundary_text,length(e.tail) AS boundary_position
                FROM edges e JOIN chunks c ON c.path=e.path AND c.ordinal=e.ordinal
                JOIN kb_documents d ON d.path=c.path
                WHERE d.archived=0 AND d.state IN ('ready','partial') AND e.head IS NOT NULL
                AND (?='' OR d.category=?) AND ('''+
                ' OR '.join('instr(lower(e.tail || e.head),lower(?))>0' for _ in terms)+
                ') ORDER BY d.created_at DESC,d.id,c.ordinal', [category,category,*terms])
            matches=[]; skipped=set();seen=set()
            for record in chain(rows,boundary):
                row=dict(record)
                key=(row['id'],row['ordinal'])
                if key in seen:continue
                value=row.get('boundary_text',row['text']); lower=value.lower()
                positions=[lower.find(term.lower()) for term in terms if term.lower() in lower]
                if 'boundary_text' in row:
                    edge=row['boundary_position']
                    if not any(0<=lower.find(term.lower())<edge<lower.find(term.lower())+len(term) for term in terms):continue
                try:
                    _, material = self._current(db, row)
                except (ValueError, OSError):
                    skipped.add(row['id']); continue
                seen.add(key)
                if offset:
                    offset -= 1; continue
                left=max(0,min(positions,default=0)-100)
                reference=citation_for(row['id'],row['sha256'],row)
                citations=[{'citation':reference,'page':row['page'],'location':row['location']}]
                if 'boundary_text' in row:
                    following=db.execute('SELECT * FROM chunks WHERE path=? AND ordinal=?',(row['path'],row['next_ordinal'])).fetchone()
                    citations.append({'citation':citation_for(row['id'],row['sha256'],following),
                        'page':following['page'],'location':following['location']})
                matches.append({'document_id': row['id'], 'title': row['title'], 'category': row['category'],
                    'citation': reference, 'citations':citations, 'sha256': row['sha256'], 'chunk': row['ordinal'],
                    'page': row['page'], 'location': row['location'], 'excerpt': value[left:left+650]})
                if len(matches)>limit:break
        return {'query':query,'matches':matches[:limit],'has_more':len(matches)>limit,
                'skipped_changed_documents':len(skipped),'notice':'结果为已上传资料的原文片段，不代表现行法律或本案事实。跨段命中请核对两处引用。'}

    def read(self, document_id, start=0, limit=4):
        with self.store.db() as db:
            document = self._document(db, document_id)
            self._current(db, document)
        result = self.store.read(document['path'], int(start), int(limit))
        for chunk in result['chunks']:
            chunk['citation'] = citation_for(document_id,document['sha256'],chunk)
        return {'document_id':document_id,'title':document['title'],**result}

    def citation(self, reference):
        match = re.fullmatch(r'KB:([0-9a-f-]{36}):(\d+):([0-9a-f]{12})(?::([0-9a-f]{16}))?', reference)
        if not match:raise ValueError('引用编号无效，请从检索结果复制。')
        identifier, ordinal, digest, parsed_digest = match.groups()
        with self.store.db() as db:
            document = self._document(db, identifier)
            source, _ = self._current(db, document)
            if document['sha256'][:12] != digest:
                raise ValueError('引用与资料版本不一致。')
            with source.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != document['sha256']:
                    raise ValueError('原件发生变化，不能引用旧索引。')
            chunk = db.execute('SELECT * FROM chunks WHERE path=? AND ordinal=?', (document['path'],int(ordinal))).fetchone()
            if chunk is None:raise ValueError('引用片段不存在。')
            if parsed_digest and parsed_digest!=chunk_digest(chunk):
                raise ValueError('引用片段的解析内容已变化，请重新检索并核对原件。')
        return {'citation': reference, 'document_id': identifier, 'title': document['title'],
                'sha256':document['sha256'], 'legacy_reference':parsed_digest is None,
                'notice':'旧引用未包含解析版本校验，请对照原件。' if parsed_digest is None else '', **dict(chunk)}

    def source(self, document_id):
        with self.store.db() as db:
            document = self._document(db, document_id, allow_archived=True)
            source, _ = self._current(db, document)
            return {'path':str(source), 'title':source.name}

    def archive(self, document_id, archived=True):
        with self.store.db() as db:
            self._document(db, document_id, allow_archived=True)
            db.execute('UPDATE kb_documents SET archived=? WHERE id=?', (int(bool(archived)), document_id))
        return {'id':document_id,'archived':bool(archived),'original_preserved':True}

    def backup(self, destination):
        from knowledge_transfer import export_backup
        target = self.store.safe(destination, internal=True, must_exist=False)
        if target.parent != self.store.internal / 'transfers':
            raise ValueError('备份暂存路径无效。')
        return export_backup(self, target)

    def restore(self, archive):
        from knowledge_transfer import restore_backup
        source = self.store.safe(archive, internal=True)
        if source.parent != self.store.internal / 'transfers':
            raise ValueError('恢复暂存路径无效。')
        return restore_backup(self, source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--workspace', required=True)
    args = parser.parse_args()
    try:
        request=json.loads(sys.stdin.read())
        allowed={'register','list','index','search','read','citation','source','archive','set_state','backup','restore'}
        if request.get('action') not in allowed:raise ValueError('不支持的知识库操作。')
        result=getattr(KnowledgeStore(args.workspace),request['action'])(**request.get('args',{}))
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
    except Exception as error:
        message=str(error) if isinstance(error,ValueError) else '知识库操作未完成，请检查文件和磁盘权限。'
        print(json.dumps({'ok':False,'error':message},ensure_ascii=False))
