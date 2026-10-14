"""Read-only pilot aliases, only after byte-for-byte matching authorized snapshots."""
from contextlib import ExitStack
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from .assets import MAX_READ, asset_path, file_hash, register_source
from .catalog import canonical, checked_path, connection, digest, ensure_root, validate_locations, writer_lock
from .csv_source import read_header, record_from_values


def import_pilot(root: Path, pilot_root: Path, source_root: Path, *, python_executable: Path | None = None, batch_id='cases-2025'):
    root, pilot_root, source_root = map(checked_path, (root, pilot_root, source_root))
    validate_locations(root, pilot_root)
    validate_locations(root, source_root)
    database = checked_path(pilot_root / 'data' / 'judgments.duckdb')
    if not database.is_file():
        raise ValueError('PILOT_DATABASE_MISSING')
    executable = checked_path(python_executable or pilot_root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
    root = ensure_root(root, create=True)
    temporary = root / ('.pilot-export-' + uuid4().hex + '.jsonl')
    before = file_hash(database)
    try:
        with temporary.open('xb') as output:
            process = subprocess.run([str(executable), '-X', 'utf8', str(Path(__file__).with_name('pilot_adapter.py')), str(database)],
                                     stdout=output, stderr=subprocess.PIPE, timeout=120,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if process.returncode != 0:
            raise ValueError('PILOT_ADAPTER_REJECTED')
        if file_hash(database) != before:
            raise ValueError('PILOT_DATABASE_CHANGED')
        with temporary.open(encoding='utf-8') as incoming:
            manifest = json.loads(next(incoming))
            if manifest.get('type') != 'sources' or not 0 <= manifest.get('count', -1) <= 10000:
                raise ValueError('PILOT_MANIFEST_INVALID')
            paths = []
            for value in manifest['paths']:
                if not Path(value).is_absolute():
                    raise ValueError('PILOT_SOURCE_OUTSIDE_SCOPE')
                path = checked_path(Path(value))
                if not path.is_relative_to(source_root) or path.suffix.lower() != '.csv':
                    raise ValueError('PILOT_SOURCE_OUTSIDE_SCOPE')
                paths.append(path)
            sources = {str(p): register_source(root, p, batch_id, 'case_csv') for p in paths}
            issues, mapped, seen = [], 0, 0
            with writer_lock(root), connection(root, writable=True) as db, ExitStack() as stack:
                files = {key: stack.enter_context(asset_path(root, src).open('rb')) for key, src in sources.items()}
                header_positions = {key: read_header(stream) for key, stream in files.items()}
                headers = {key: value[0] for key, value in header_positions.items()}
                for key, (header, first) in header_positions.items():
                    # A pilot can be noncontiguous. Record the verified header but
                    # leave the full-file import at its very first record.
                    existing = db.execute('SELECT header_json FROM import_states WHERE source_id=?', (sources[key].source_id,)).fetchone()
                    if existing and json.loads(existing[0]) != header:
                        raise ValueError('SOURCE_CHANGED_HEADER')
                    db.execute('INSERT OR IGNORE INTO import_states VALUES(?,?,?,?,?)',
                               (sources[key].source_id, 1, first, canonical(header), 'partial'))
                for line in incoming:
                    seen += 1
                    if seen > manifest['count']:
                        raise ValueError('PILOT_MANIFEST_INVALID')
                    row = json.loads(line)
                    alias = row['record_id']
                    if not isinstance(alias, str) or not re.fullmatch('[a-f0-9]{64}', alias):
                        raise ValueError('PILOT_ALIAS_INVALID')
                    key = str(checked_path(Path(row['source_file'])))
                    if key not in sources:
                        raise ValueError('PILOT_SOURCE_OUTSIDE_SCOPE')
                    source = sources[key]
                    start, end, ordinal = row['byte_start'], row['byte_end'], row['ordinal']
                    if any(type(v) is not int for v in (start, end, ordinal)) or ordinal < 1 or not 0 <= start <= end <= source.size or end - start > MAX_READ:
                        issues.append({'record_id': alias, 'reason': 'PILOT_RANGE_INVALID'})
                        continue
                    stream = files[key]
                    stream.seek(start)
                    raw = stream.read(end - start)
                    if digest(raw) != row['raw_sha256']:
                        issues.append({'record_id': alias, 'reason': 'PILOT_BYTES_MISMATCH'})
                        continue
                    try:
                        parsed = list(csv.reader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True))
                        if len(parsed) != 1:
                            raise ValueError
                        record = record_from_values(source, ordinal, start, end, raw, headers[key], parsed[0])
                    except (UnicodeDecodeError, csv.Error, ValueError):
                        issues.append({'record_id': alias, 'reason': 'PILOT_RECORD_INVALID'})
                        continue
                    if record.body_sha256 != row['body_sha256']:
                        issues.append({'record_id': alias, 'reason': 'PILOT_BODY_MISMATCH'})
                        continue
                    old = db.execute('SELECT raw_sha256 FROM records WHERE record_id=?', (record.record_id,)).fetchone()
                    old_alias = db.execute('SELECT record_id FROM record_aliases WHERE alias=?', (alias,)).fetchone()
                    collision = db.execute('SELECT record_id FROM records WHERE record_id=?', (alias,)).fetchone()
                    if old and old[0] != record.raw_sha256 or old_alias and old_alias[0] != record.record_id or collision and alias != record.record_id:
                        raise ValueError('PILOT_ALIAS_CONFLICT')
                    db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?)',
                               (record.record_id, source.source_id, ordinal, record.raw_sha256, record.model_dump_json()))
                    db.execute('INSERT OR IGNORE INTO record_aliases VALUES(?,?)', (alias, record.record_id))
                    mapped += 1
                    if mapped % 1000 == 0:
                        db.commit()
                if seen != manifest['count']:
                    raise ValueError('PILOT_MANIFEST_INVALID')
            return {'mapped': mapped, 'mismatched': len(issues), 'issues': issues, 'pilot_sha256': before}
    finally:
        if temporary.exists():
            temporary.unlink()
