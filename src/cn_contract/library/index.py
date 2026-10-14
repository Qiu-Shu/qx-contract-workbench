"""Derived, immutable search generations; a small pointer is the publication unit."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from ..domain import LibraryFragment
from .assets import file_hash
from .catalog import canonical, checked_path, connection, digest, ensure_root, iter_records, writer_lock
from .originals import OriginalReader
from .text import TOKENIZER_VERSION, normalize, tokens


def generation_path(root, generation_id):
    root = ensure_root(root)
    if not isinstance(generation_id, str) or not re.fullmatch('[a-f0-9]{32}', generation_id):
        raise ValueError('GENERATION_ID_INVALID')
    return checked_path(root / 'generations' / generation_id)


def build_generation(root: Path, record_ids=None) -> str:
    with writer_lock(root) as root:
        generation_id = uuid4().hex
        directory = generation_path(root, generation_id)
        directory.mkdir(parents=True)
        selected = set(record_ids) if record_ids is not None else None
        database_path = directory / 'search.sqlite'
        db = sqlite3.connect(database_path)
        counts = {'records': 0, 'case_csv': 0, 'law_markdown': 0, 'units': 0}
        try:
            db.executescript('''
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=FULL;
                PRAGMA cache_size=-65536;
                CREATE TABLE units (
                    rowid INTEGER PRIMARY KEY, unit_id TEXT NOT NULL UNIQUE, record_id TEXT NOT NULL,
                    version_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
                    case_no TEXT, court TEXT, cause TEXT, province TEXT, decision_date TEXT,
                    fragment_id TEXT, start INTEGER NOT NULL, end INTEGER NOT NULL,
                    article TEXT, ambiguous INTEGER NOT NULL
                );
                CREATE INDEX ix_units_case ON units(case_no);
                CREATE INDEX ix_units_filters ON units(kind,province,decision_date);
                CREATE VIRTUAL TABLE search USING fts5(title_tokens,body_tokens,content='',detail=full,
                    tokenize='unicode61 remove_diacritics 0');
            ''')
            with OriginalReader(root, preload=True) as reader, connection(root) as catalog:
                for record in iter_records(root):
                    if selected is not None and record.record_id not in selected:
                        continue
                    original, _, _ = reader.read(record)
                    if record.kind == 'law_markdown':
                        fragments = [LibraryFragment.model_validate_json(row[0]) for row in
                                     catalog.execute('SELECT fragment_json FROM fragments WHERE record_id=? ORDER BY ordinal', (record.record_id,))]
                    else:
                        fragments = [None]
                    title = record.fields.get('title') or record.fields.get('case_no') or '未命名资料'
                    title_tokens = ' '.join(tokens(normalize(title)))
                    for fragment in fragments:
                        start, end = (fragment.start, fragment.end) if fragment else (0, len(original))
                        if fragment and digest(original[start:end].encode('utf-8')) != fragment.text_sha256:
                            raise ValueError('FRAGMENT_HASH_MISMATCH')
                        unit_id = fragment.fragment_id if fragment else record.record_id
                        cursor = db.execute('INSERT INTO units(unit_id,record_id,version_id,kind,title,case_no,court,cause,province,decision_date,fragment_id,start,end,article,ambiguous) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (unit_id, record.record_id, record.version_id, record.kind, title,
                             record.fields.get('case_no'), record.fields.get('court'), record.fields.get('cause'),
                             record.fields.get('province') or record.fields.get('region_candidate'), record.fields.get('decision_date'),
                             fragment.fragment_id if fragment else None, start, end,
                             fragment.article if fragment else None, int(fragment.ambiguous) if fragment else 0))
                        db.execute('INSERT INTO search(rowid,title_tokens,body_tokens) VALUES(?,?,?)',
                                   (cursor.lastrowid, title_tokens, ' '.join(tokens(normalize(original[start:end])))))
                        counts['units'] += 1
                    counts['records'] += 1
                    counts[record.kind] += 1
                    if counts['records'] % 500 == 0:
                        db.commit()
            db.commit()
            db.execute("INSERT INTO search(search) VALUES('integrity-check')")
            db.commit()
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('INDEX_INTEGRITY_FAILED')
        finally:
            db.close()
        info = database_path.stat()
        manifest = {'generation_id': generation_id, 'state': 'ready', 'tokenizer': TOKENIZER_VERSION,
                    'coverage': counts, 'index_sha256': file_hash(database_path), 'index_bytes': info.st_size,
                    'index_mtime_ns': info.st_mtime_ns, 'created_at': datetime.now(timezone.utc).isoformat()}
        (directory / 'manifest.json').write_text(canonical(manifest), encoding='utf-8')
        return generation_id


def validate_generation(root, generation_id):
    directory = generation_path(root, generation_id)
    path = checked_path(directory / 'manifest.json')
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('INDEX_NOT_READY')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('generation_id') != generation_id or manifest.get('state') != 'ready' or manifest.get('tokenizer') != TOKENIZER_VERSION:
        raise ValueError('INDEX_NOT_READY')
    database = checked_path(directory / 'search.sqlite')
    if database.stat().st_size != manifest['index_bytes'] or file_hash(database) != manifest['index_sha256']:
        raise ValueError('INDEX_HASH_MISMATCH')
    return manifest


def activate_generation(root, generation_id):
    with writer_lock(root) as root:
        validate_generation(root, generation_id)
        directory = generation_path(root, generation_id)
        manifest_bytes = (directory / 'manifest.json').read_bytes()
        pointer = {'generation_id': generation_id, 'manifest_sha256': digest(manifest_bytes)}
        temporary = root / ('.current-' + uuid4().hex)
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                stream.write(canonical(pointer))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, root / 'current.json')
        finally:
            if temporary.exists():
                temporary.unlink()


def current_generation(root):
    root = Path(root)
    if not root.exists():
        return None
    root = ensure_root(root)
    pointer_path = root / 'current.json'
    if not pointer_path.exists():
        return None
    if pointer_path.stat().st_size > 8192:
        raise ValueError('INDEX_POINTER_INVALID')
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    directory = generation_path(root, pointer['generation_id'])
    manifest_path = checked_path(directory / 'manifest.json')
    if manifest_path.stat().st_size > 65536:
        raise ValueError('INDEX_MANIFEST_INVALID')
    raw = manifest_path.read_bytes()
    if digest(raw) != pointer['manifest_sha256']:
        raise ValueError('INDEX_MANIFEST_CHANGED')
    manifest = json.loads(raw)
    if manifest.get('state') != 'ready' or manifest.get('tokenizer') != TOKENIZER_VERSION:
        raise ValueError('INDEX_NOT_READY')
    info = checked_path(directory / 'search.sqlite').stat()
    if info.st_size != manifest['index_bytes'] or info.st_mtime_ns != manifest['index_mtime_ns']:
        raise ValueError('INDEX_CHANGED')
    return manifest
