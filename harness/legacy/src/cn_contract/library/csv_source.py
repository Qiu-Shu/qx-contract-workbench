"""Strict CSV records with exact byte offsets and transaction-backed checkpoints."""
import csv
import json
from pathlib import Path

from ..domain import LibraryRecord, LibrarySource
from .assets import MAX_READ, asset_path, file_hash, register_source
from .catalog import canonical, checked_path, connection, digest, writer_lock
from .cleaning import clean_case

csv.field_size_limit(MAX_READ)


class CsvParseFailure(ValueError):
    def __init__(self, ordinal: int, offset: int, reason: str):
        super().__init__('CSV_PARSE_ABORT')
        self.ordinal, self.offset, self.reason = ordinal, offset, reason


class Lines:
    """Preserves quoted multiline bytes, reusing the prior pilot's parsing contract."""
    def __init__(self, stream):
        self.stream = stream
        self.reset()

    def reset(self):
        self.parts = []
        self.size = 0

    def __iter__(self):
        return self

    def __next__(self):
        start = self.stream.tell()
        line = self.stream.readline(MAX_READ - self.size + 1)
        if not line:
            raise StopIteration
        self.size += len(line)
        if self.size > MAX_READ:
            raise ValueError('RECORD_TOO_LARGE')
        self.parts.append(line)
        return line.decode('utf-8-sig' if start == 0 else 'utf-8', errors='strict')


def read_header(stream):
    stream.seek(0)
    try:
        header = next(csv.reader(Lines(stream), strict=True))
    except (StopIteration, csv.Error, UnicodeDecodeError, ValueError):
        raise ValueError('HEADER_INVALID') from None
    if len(set(header)) != len(header) or not {'案号', '文书内容'} <= set(header):
        raise ValueError('HEADER_INVALID')
    return header, stream.tell()


def record_from_values(source, ordinal, start, end, raw, header, values):
    valid = len(header) == len(values)
    original = dict(zip(header, values)) if valid else {}
    cleaned = clean_case(original)
    body = original.get('文书内容', '')
    raw_hash = digest(raw)
    body_hash = digest(body.encode('utf-8')) if body else None
    return LibraryRecord(
        record_id=digest(canonical(['qx-library-v1', source.batch_id, source.sha256, ordinal]).encode('utf-8')),
        source_id=source.source_id, kind=source.kind, ordinal=ordinal, byte_start=start, byte_end=end,
        raw_sha256=raw_hash, body_sha256=body_hash, version_id=body_hash or raw_hash,
        fields=cleaned['fields'], warnings=cleaned['warnings'] + (() if valid else ('column_count',)),
        body_status=('body_present_unverified' if body.strip() else 'catalog_only') if valid else 'damaged_record')


def iter_case_records(root: Path, source: LibrarySource, start_ordinal: int = 1, start_byte: int = 0):
    if type(start_ordinal) is not int or start_ordinal < 1 or type(start_byte) is not int or start_byte < 0 or start_byte > source.size:
        raise ValueError('CHECKPOINT_INVALID')
    path = asset_path(root, source)
    if file_hash(path) != source.sha256:
        raise ValueError('ASSET_HASH_MISMATCH')
    with path.open('rb') as stream:
        header, first = read_header(stream)
        if start_byte and start_byte < first or start_ordinal != 1 and not start_byte:
            raise ValueError('CHECKPOINT_INVALID')
        stream.seek(start_byte or first)
        lines = Lines(stream)
        reader = csv.reader(lines, strict=True)
        ordinal = start_ordinal
        while True:
            lines.reset()
            start = stream.tell()
            try:
                values = next(reader)
            except StopIteration:
                return
            except (csv.Error, UnicodeDecodeError, ValueError) as error:
                raise CsvParseFailure(ordinal, start, type(error).__name__) from None
            yield record_from_values(source, ordinal, start, stream.tell(), b''.join(lines.parts), header, values)
            ordinal += 1


def _commit_batch(db, source, records, header):
    if not records:
        return 0
    existing = dict(db.execute('SELECT ordinal,raw_sha256 FROM records WHERE source_id=? AND ordinal BETWEEN ? AND ?',
                              (source.source_id, records[0].ordinal, records[-1].ordinal)).fetchall())
    for record in records:
        if record.ordinal in existing and existing[record.ordinal] != record.raw_sha256:
            raise ValueError('RECORD_REPLAY_MISMATCH')
    db.executemany('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?)',
                   [(r.record_id, r.source_id, r.ordinal, r.raw_sha256, r.model_dump_json()) for r in records])
    db.executemany('INSERT OR IGNORE INTO failures VALUES(?,?,?,?)',
                   [(r.source_id, r.ordinal, r.byte_start, 'COLUMN_COUNT') for r in records if r.body_status == 'damaged_record'])
    last = records[-1]
    db.execute('INSERT INTO import_states VALUES(?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET next_ordinal=excluded.next_ordinal,next_byte=excluded.next_byte,state=excluded.state',
               (source.source_id, last.ordinal + 1, last.byte_end, canonical(header), 'partial'))
    db.commit()
    return len(records) - len(existing)


def import_case_file(root: Path, path: Path, batch_id: str, *, limit: int | None = None, batch_size=1000):
    from .budget import check_budget
    if limit is not None and (type(limit) is not int or limit < 1) or type(batch_size) is not int or not 1 <= batch_size <= 10000:
        raise ValueError('IMPORT_LIMIT_INVALID')
    root, path = Path(root), checked_path(path)
    check_budget(root, force=True)
    source = None
    if (root / 'library.json').exists():
        with connection(root) as db:
            for row in db.execute('SELECT source_json FROM sources WHERE batch_id=? AND kind=?', (batch_id, 'case_csv')):
                candidate = LibrarySource.model_validate_json(row[0])
                if str(path) in candidate.aliases:
                    if file_hash(path) != candidate.sha256:
                        raise ValueError('SOURCE_CHANGED')
                    source = candidate
                    break
    if source is None:
        source = register_source(root, path, batch_id, 'case_csv')
    inserted = 0
    with writer_lock(root), connection(root, writable=True) as db:
        with asset_path(root, source).open('rb') as stream:
            header, first = read_header(stream)
        state = db.execute('SELECT * FROM import_states WHERE source_id=?', (source.source_id,)).fetchone()
        if state is not None and json.loads(state['header_json']) != header:
            raise ValueError('SOURCE_CHANGED_HEADER')
        start_ordinal, start_byte = (state['next_ordinal'], state['next_byte']) if state else (1, first)
        db.execute('INSERT OR IGNORE INTO import_states VALUES(?,?,?,?,?)',
                   (source.source_id, start_ordinal, start_byte, canonical(header), 'partial'))
        db.commit()
        batch = []
        if state is None or state['state'] != 'complete':
            records = iter_case_records(root, source, start_ordinal, start_byte)
            try:
                ordinal = start_ordinal
                reached_eof = False
                while limit is None or ordinal <= limit:
                    try:
                        record = next(records)
                    except StopIteration:
                        reached_eof = True
                        break
                    batch.append(record)
                    ordinal += 1
                    if len(batch) >= batch_size:
                        inserted += _commit_batch(db, source, batch, header)
                        batch = []
                        check_budget(root)
                inserted += _commit_batch(db, source, batch, header)
                position = db.execute('SELECT next_byte FROM import_states WHERE source_id=?', (source.source_id,)).fetchone()[0]
                if reached_eof or position == source.size:
                    db.execute("UPDATE import_states SET state='complete' WHERE source_id=?", (source.source_id,))
            except CsvParseFailure as error:
                inserted += _commit_batch(db, source, batch, header)
                db.execute('INSERT OR IGNORE INTO failures VALUES(?,?,?,?)', (source.source_id, error.ordinal, error.offset, 'PARSE_ABORT'))
                db.execute("UPDATE import_states SET state='parse_aborted' WHERE source_id=?", (source.source_id,))
            finally:
                records.close()
        db.commit()
        state = db.execute('SELECT * FROM import_states WHERE source_id=?', (source.source_id,)).fetchone()
        stored = db.execute('SELECT count(*) FROM records WHERE source_id=?', (source.source_id,)).fetchone()[0]
        failed = db.execute('SELECT count(*) FROM failures WHERE source_id=?', (source.source_id,)).fetchone()[0]
    return {'source_id': source.source_id, 'stored': stored, 'inserted': inserted, 'failed': failed,
            'state': state['state'], 'complete': state['state'] == 'complete',
            'next_ordinal': state['next_ordinal'], 'next_byte': state['next_byte']}
