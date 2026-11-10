"""Portable source directory and append-only human review notes."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from ..domain import LibraryRecord, LibraryReviewEvent, LibrarySource
from ..ops.file_paths import sqlite_readonly_uri

FORMAT = {'format': 'qx-legal-library', 'version': 1}


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def checked_path(path: Path) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('REDIRECTED_PATH')
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError('REDIRECTED_FILE')
    return path.resolve()


def validate_locations(root: Path, source: Path) -> None:
    root, source = checked_path(root), checked_path(source)
    if root == source or source.is_relative_to(root) or source.is_dir() and root.is_relative_to(source):
        raise ValueError('SOURCE_OUTPUT_OVERLAP')


def ensure_root(root: Path, *, create=False) -> Path:
    root = checked_path(root)
    marker = checked_path(root / 'library.json')
    if marker.exists():
        if marker.stat().st_size > 4096 or json.loads(marker.read_text(encoding='utf-8')) != FORMAT:
            raise ValueError('LIBRARY_FORMAT_INVALID')
    elif create:
        if root.exists() and any(root.iterdir()):
            raise ValueError('LIBRARY_NOT_INITIALIZED')
        root.mkdir(parents=True, exist_ok=True)
        with marker.open('x', encoding='utf-8') as stream:
            stream.write(canonical(FORMAT))
    else:
        raise ValueError('LIBRARY_NOT_INITIALIZED')
    for name in ('assets', 'generations', 'catalog.sqlite', 'catalog.sqlite-wal',
                 'catalog.sqlite-shm', 'catalog.sqlite-journal', '.writer.lock', 'current.json'):
        checked_path(root / name)
    return root


@contextmanager
def writer_lock(root: Path):
    root = ensure_root(root, create=True)
    with (root / '.writer.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('LIBRARY_BUSY') from None
        try:
            yield root
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def connection(root: Path, *, writable=False):
    root = ensure_root(root, create=writable)
    path = root / 'catalog.sqlite'
    db = sqlite3.connect(str(path) if writable else sqlite_readonly_uri(path), uri=not writable)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        if writable:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                    batch_id TEXT NOT NULL, kind TEXT NOT NULL, source_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    seq INTEGER PRIMARY KEY, subject_id TEXT NOT NULL, version_id TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE, previous_hash TEXT, event_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    record_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
                    ordinal INTEGER NOT NULL, raw_sha256 TEXT NOT NULL, record_json TEXT NOT NULL,
                    UNIQUE(source_id,ordinal)
                );
                CREATE TABLE IF NOT EXISTS import_states (
                    source_id TEXT PRIMARY KEY REFERENCES sources(source_id), next_ordinal INTEGER NOT NULL,
                    next_byte INTEGER NOT NULL, header_json TEXT NOT NULL, state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS failures (
                    source_id TEXT NOT NULL REFERENCES sources(source_id), ordinal INTEGER NOT NULL,
                    byte_start INTEGER NOT NULL, reason TEXT NOT NULL,
                    PRIMARY KEY(source_id,ordinal,reason)
                );
                CREATE TABLE IF NOT EXISTS record_aliases (
                    alias TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(record_id)
                );
                CREATE TABLE IF NOT EXISTS fragments (
                    fragment_id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(record_id),
                    ordinal INTEGER NOT NULL, fragment_json TEXT NOT NULL,
                    UNIQUE(record_id,ordinal)
                );
                CREATE TRIGGER IF NOT EXISTS review_no_update BEFORE UPDATE ON reviews
                BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
                CREATE TRIGGER IF NOT EXISTS review_no_delete BEFORE DELETE ON reviews
                BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
            ''')
        yield db
        if writable:
            db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def get_source(root: Path, source_id: str) -> LibrarySource:
    with connection(root) as db:
        return _get_source(db, source_id)


def _get_source(db, source_id: str) -> LibrarySource:
    if not isinstance(source_id, str) or len(source_id) != 64 or any(c not in '0123456789abcdef' for c in source_id):
        raise ValueError('SOURCE_ID_INVALID')
    row = db.execute('SELECT source_json FROM sources WHERE source_id=?', (source_id,)).fetchone()
    if row is None:
        raise ValueError('SOURCE_NOT_FOUND')
    return LibrarySource.model_validate_json(row[0])


def append_review(root: Path, event: LibraryReviewEvent) -> str:
    event = LibraryReviewEvent.model_validate(event.model_dump(mode='json'))
    with writer_lock(root), connection(root, writable=True) as db:
        previous = db.execute('SELECT event_hash FROM reviews ORDER BY seq DESC LIMIT 1').fetchone()
        previous_hash = previous[0] if previous else None
        payload = canonical(event.model_dump(mode='json'))
        event_hash = digest(canonical([previous_hash, json.loads(payload)]).encode('utf-8'))
        db.execute('INSERT INTO reviews(subject_id,version_id,event_hash,previous_hash,event_json) VALUES(?,?,?,?,?)',
                   (event.subject_id, event.version_id, event_hash, previous_hash, payload))
    return event_hash


def iter_records(root: Path, source_id: str | None = None):
    with connection(root) as db:
        query = 'SELECT record_json FROM records'
        args = ()
        if source_id is not None:
            query += ' WHERE source_id=?'
            args = (source_id,)
        for row in db.execute(query + ' ORDER BY source_id,ordinal', args):
            yield LibraryRecord.model_validate_json(row[0])


def get_record(root: Path, record_id: str) -> LibraryRecord:
    with connection(root) as db:
        return _get_record(db, record_id)


def _get_record(db, record_id: str) -> LibraryRecord:
    row = db.execute('SELECT record_json FROM records WHERE record_id=?', (record_id,)).fetchone()
    if row is None:
        row = db.execute('SELECT r.record_json FROM records r JOIN record_aliases a ON a.record_id=r.record_id WHERE a.alias=?', (record_id,)).fetchone()
    if row is None:
        raise ValueError('RECORD_NOT_FOUND')
    return LibraryRecord.model_validate_json(row[0])
