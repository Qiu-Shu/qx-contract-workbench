"""Conservative law-file versions and complete, source-coordinate fragments."""
from collections import Counter
from datetime import date
import os
from pathlib import Path
import re
import unicodedata

from ..domain import LibraryFragment, LibraryRecord
from .assets import MAX_READ, asset_path, _register_source_in_transaction
from .budget import check_budget
from .catalog import canonical, checked_path, connection, digest, validate_locations, writer_lock

INVISIBLE = '\u200b\u200c\u200d\u2060\ufeff'
ARTICLE = re.compile(r'^第([零〇一二三四五六七八九十百千万两0-9]+)条(?:之([零〇一二三四五六七八九十百千万两0-9]+))?')
JILIN_NAMES = ('吉林', '长春', '四平', '通化', '白山', '辽源', '松原', '白城', '延边')


def _visible(value):
    return unicodedata.normalize('NFKC', value.translate(str.maketrans('', '', INVISIBLE)))


def law_fields(path: Path, original: str):
    name = _visible(path.stem).strip(' +')
    name = re.sub(r'[_（(]?转自DOC[）)]?$', '', name, flags=re.I).rstrip('_')
    match = re.search(r'[_-](\d{8})$', name)
    warnings = []
    candidate_date = None
    if match:
        digits = match[1]
        name = name[:match.start()].rstrip(' _-')
        try:
            candidate_date = date(int(digits[:4]), int(digits[4:6]), int(digits[6:])).isoformat()
        except ValueError:
            warnings.append('invalid_filename_date')
    else:
        warnings.append('missing_filename_date')
    region = '吉林省' if any(value in name for value in JILIN_NAMES) else None
    if region is None and name.startswith('中华人民共和国'):
        region = '全国'
    urls = re.findall(r'https?://[^\s<>"\]\)]+', original)
    if not urls:
        warnings.append('missing_source_url')
    if any(char in original for char in INVISIBLE):
        warnings.append('zero_width')
    if not original.strip():
        warnings.append('empty_text')
    series = digest(canonical([re.sub(r'\s+', '', name), region, None]).encode('utf-8'))
    return {
        'title': name or path.stem, 'filename': path.name, 'filename_date_candidate': candidate_date,
        'region_candidate': region, 'issuer_candidate': None, 'source_url': None,
        'source_url_candidate': urls[0] if urls else None, 'effective_from': None, 'effective_to': None,
        'legal_status': 'unknown', 'series_id': series, 'series_status': 'machine_candidate',
    }, tuple(warnings)


def split_law(record: LibraryRecord, original: str) -> tuple[LibraryFragment, ...]:
    lines = original.splitlines(keepends=True)
    nonempty = [line for line in lines if line.strip()]
    mostly_quoted = bool(nonempty) and sum(line.lstrip().startswith('>') for line in nonempty) > len(nonempty) / 2
    boundaries = [(0, None, 'paragraph')]
    seen = Counter()
    in_contents = False
    offset = 0
    for line in lines:
        visible = _visible(line).strip()
        quoted = visible.startswith('>')
        plain = re.sub(r'^(?:#{1,6}\s*|>\s*)+', '', visible)
        if re.fullmatch(r'目\s*录', plain):
            in_contents = True
        match = ARTICLE.match(plain)
        if match:
            label = match[0]
            tail = plain[match.end():].strip()
            if in_contents and (seen[label] and tail or len(tail) > 18):
                in_contents = False
            role = ('contents_candidate' if in_contents else
                    'quoted_candidate' if quoted and not mostly_quoted else 'article_candidate')
            if offset == 0:
                boundaries[0] = (0, label, role)
            else:
                boundaries.append((offset, label, role))
            seen[label] += 1
        offset += len(line)
    duplicates = Counter(label for _, label, role in boundaries if label and role != 'contents_candidate')
    fragments = []
    for index, (start, article, role) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(original)
        cursor = start
        while cursor < end or cursor == end == 0:
            stop = min(cursor + 4000, end)
            if stop < end:
                newline = original.rfind('\n', cursor + 1, stop)
                if newline > cursor:
                    stop = newline + 1
            text_hash = digest(original[cursor:stop].encode('utf-8'))
            fragment_id = digest(canonical([record.record_id, record.version_id, cursor, stop, text_hash]).encode('utf-8'))
            fragments.append(LibraryFragment(fragment_id=fragment_id, record_id=record.record_id,
                version_id=record.version_id, ordinal=len(fragments) + 1, start=cursor, end=stop,
                line_start=original.count('\n', 0, cursor) + 1,
                line_end=original.count('\n', 0, max(cursor, stop - 1)) + 1,
                text_sha256=text_hash, role=role, article=article,
                ambiguous=bool(article and duplicates[article] > 1)))
            if stop == end:
                break
            cursor = stop
    return tuple(fragments)


def iter_fragments(root: Path, record_id: str | None = None):
    with connection(root) as db:
        query = 'SELECT fragment_json FROM fragments'
        args = ()
        if record_id is not None:
            query += ' WHERE record_id=?'
            args = (record_id,)
        for row in db.execute(query + ' ORDER BY record_id,ordinal', args):
            yield LibraryFragment.model_validate_json(row[0])


def import_laws(root: Path, input_dir: Path, batch_id: str, *, batch_size=100) -> dict:
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError('IMPORT_LIMIT_INVALID')
    input_dir = checked_path(input_dir)
    validate_locations(root, input_dir)
    if not input_dir.is_dir():
        raise ValueError('LAW_DIRECTORY_REQUIRED')
    paths = []
    for directory, folders, files in os.walk(input_dir, followlinks=False):
        for folder in folders:
            checked_path(Path(directory) / folder)
        for filename in files:
            if Path(filename).suffix.lower() == '.md':
                paths.append(checked_path(Path(directory) / filename))
    unique, issues, inserted = set(), [], 0
    with writer_lock(root) as root, connection(root, writable=True) as db:
        check_budget(root, force=True)
        for position, path in enumerate(sorted(paths), 1):
            source = _register_source_in_transaction(root, path, batch_id, 'law_markdown', db)
            if source.size > MAX_READ:
                reason = 'LAW_TOO_LARGE'
            else:
                try:
                    raw = asset_path(root, source).read_bytes()
                    if digest(raw) != source.sha256:
                        raise ValueError('ASSET_HASH_MISMATCH')
                    original = raw.decode('utf-8-sig', errors='strict')
                    reason = None
                except UnicodeDecodeError:
                    reason = 'LAW_DECODE_FAILED'
            if reason:
                issues.append({'file': str(path.relative_to(input_dir)), 'reason': reason})
                db.execute('INSERT OR IGNORE INTO failures VALUES(?,?,?,?)', (source.source_id, 1, 0, reason))
            else:
                fields, warnings = law_fields(path, original)
                body_hash = digest(original.encode('utf-8'))
                record = LibraryRecord(
                    record_id=digest(canonical(['qx-library-v1', source.batch_id, source.sha256, 1]).encode('utf-8')),
                    source_id=source.source_id, kind='law_markdown', ordinal=1, byte_start=0, byte_end=source.size,
                    raw_sha256=source.sha256, body_sha256=body_hash, version_id=body_hash,
                    fields=fields, warnings=warnings, body_status='body_present_unverified' if original.strip() else 'catalog_only')
                unique.add(record.record_id)
                previous = db.execute('SELECT raw_sha256 FROM records WHERE record_id=?', (record.record_id,)).fetchone()
                if previous:
                    if previous[0] != record.raw_sha256:
                        raise ValueError('RECORD_REPLAY_MISMATCH')
                else:
                    db.execute('INSERT INTO records VALUES(?,?,?,?,?)',
                               (record.record_id, source.source_id, 1, source.sha256, record.model_dump_json()))
                    fragments = split_law(record, original)
                    db.executemany('INSERT INTO fragments VALUES(?,?,?,?)',
                                   [(f.fragment_id, f.record_id, f.ordinal, f.model_dump_json()) for f in fragments])
                    db.execute('INSERT INTO import_states VALUES(?,?,?,?,?)', (source.source_id, 2, source.size, '[]', 'complete'))
                    inserted += 1
            if position % batch_size == 0:
                db.commit()
                check_budget(root)
    return {'files': len(paths), 'unique_records': len(unique), 'inserted': inserted,
            'failed': len(issues), 'issues': issues}
