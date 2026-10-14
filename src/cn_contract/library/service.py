"""Read-only retrieval shared by CLI and authenticated workbench routes."""
import base64
import json
from pathlib import Path
import sqlite3
import time

from ..domain import LibraryFragment, LibraryHit, LibraryOriginal, LibraryPage, LibraryQuery
from .catalog import canonical, connection, digest, get_record
from .cleaning import normalize_case
from .index import current_generation, generation_path
from .originals import OriginalReader
from .text import normalize, query_terms


def read_original(root: Path, record_id: str, version_id: str) -> LibraryOriginal:
    record = get_record(root, record_id)
    if record.version_id != version_id:
        raise ValueError('VERSION_MISMATCH')
    with OriginalReader(root) as reader:
        text, fields, source = reader.read(record)
    return LibraryOriginal(record=record, source=source, text=text, raw_fields=fields)


def read_fragment(root: Path, fragment_id: str) -> LibraryOriginal:
    with connection(root) as db:
        row = db.execute('SELECT fragment_json FROM fragments WHERE fragment_id=?', (fragment_id,)).fetchone()
    if row is None:
        raise ValueError('FRAGMENT_NOT_FOUND')
    fragment = LibraryFragment.model_validate_json(row[0])
    original = read_original(root, fragment.record_id, fragment.version_id)
    if digest(original.text[fragment.start:fragment.end].encode('utf-8')) != fragment.text_sha256:
        raise ValueError('FRAGMENT_HASH_MISMATCH')
    return original.model_copy(update={'fragment': fragment})


def _cursor_encode(generation_id, query_hash, offset):
    return base64.urlsafe_b64encode(canonical([generation_id, query_hash, offset]).encode()).decode()


def _cursor_decode(cursor, generation_id, query_hash):
    if cursor is None:
        return 0
    try:
        value = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
    except (ValueError, UnicodeError):
        raise ValueError('CURSOR_INVALID') from None
    if not isinstance(value, list) or len(value) != 3 or value[:2] != [generation_id, query_hash]:
        raise ValueError('CURSOR_STALE_OR_DIFFERENT_QUERY')
    if type(value[2]) is not int or not 0 <= value[2] <= 10000000:
        raise ValueError('CURSOR_INVALID')
    if value[2] >= 2000:
        raise ValueError('CURSOR_TOO_DEEP')
    return value[2]


def search(root: Path, query: LibraryQuery) -> LibraryPage:
    query = LibraryQuery.model_validate(query.model_dump(mode='json'))
    terms, expression = query_terms(query.text, query.mode)
    manifest = current_generation(root)
    if manifest is None:
        return LibraryPage(state='not_ready')
    generation_id = manifest['generation_id']
    query_hash = digest(canonical(query.model_dump(mode='json', exclude={'cursor'})).encode('utf-8'))
    offset = _cursor_decode(query.cursor, generation_id, query_hash)
    predicates, args = [], []
    if expression:
        predicates.append('search MATCH ?')
        args.append(expression)
    if query.kind != 'all':
        predicates.append('u.kind=?')
        args.append(query.kind)
    for name in ('case_no', 'court', 'cause', 'province', 'document_type'):
        value = getattr(query, name)
        if value is not None:
            predicates.append('u.' + name + '=?')
            args.append(normalize_case(value) if name == 'case_no' else value)
    for name, op in (('date_from', '>='), ('date_to', '<=')):
        value = getattr(query, name)
        if value is not None:
            predicates.append('u.decision_date' + op + '?')
            args.append(value.isoformat())
    rank = 'bm25(search,8.0,1.0)' if expression else '0.0'
    sql = 'SELECT u.*,' + rank + ' AS score FROM units u'
    if expression:
        sql += ' JOIN search ON search.rowid=u.rowid'
    if predicates:
        sql += ' WHERE ' + ' AND '.join(predicates)
    sql += (' ORDER BY score,u.unit_id' if expression else ' ORDER BY u.unit_id') + ' LIMIT -1 OFFSET ?'
    args.append(offset)
    database = generation_path(root, generation_id) / 'search.sqlite'
    db = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    deadline = time.monotonic() + 2.0
    db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 5000)
    hits, consumed, more, state = [], 0, False, 'ready'
    try:
        with OriginalReader(root) as reader:
            cursor = db.execute(sql, args)
            while True:
                if time.monotonic() >= deadline:
                    state, more = 'timeout', True
                    break
                row = cursor.fetchone()
                if row is None:
                    break
                consumed += 1
                record = get_record(root, row['record_id'])
                if record.version_id != row['version_id']:
                    raise ValueError('INDEX_VERSION_MISMATCH')
                text, _, _ = reader.read(record)
                section = text[row['start']:row['end']]
                normalized, mapping = normalize(section, with_map=True)
                titles = [normalize(value) for value in [row['title'], *json.loads(row['title_aliases'])]]
                if any(term not in normalized and all(term not in title for title in titles) for term in terms):
                    continue
                starts = [(normalized.find(term), term) for term in terms if term in normalized]
                if starts:
                    start, term = min(starts)
                    match_start = row['start'] + mapping[start]
                    match_end = row['start'] + mapping[start + len(term) - 1] + 1
                    field = 'body'
                else:
                    match_start = match_end = None
                    field = 'title' if terms else 'metadata'
                excerpt_start = max(row['start'], (match_start or row['start']) - 60)
                snippet = text[excerpt_start:min(row['end'], excerpt_start + 220)]
                hits.append(LibraryHit(record_id=record.record_id, version_id=record.version_id,
                    fragment_id=row['fragment_id'], kind=record.kind, title=row['title'], snippet=snippet,
                    match_start=match_start, match_end=match_end, match_field=field, score=row['score'],
                    fields=record.fields, body_status=record.body_status,
                    article=row['article'], ambiguous=bool(row['ambiguous'])))
                if len(hits) >= query.limit:
                    more = True
                    break
    except sqlite3.OperationalError:
        if time.monotonic() < deadline:
            raise
        state, more = 'timeout', True
    finally:
        db.close()
    return LibraryPage(hits=tuple(hits), generation_id=generation_id, coverage=manifest['coverage'], state=state,
                       next_cursor=_cursor_encode(generation_id, query_hash, offset + consumed) if more else None,
                       total_matches=len(hits) if not more and offset == 0 else None)
