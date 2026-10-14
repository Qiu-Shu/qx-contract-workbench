"""Immutable byte snapshots. Original locations are aliases, never storage IDs."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
from uuid import uuid4

from ..domain import LibrarySource
from .catalog import canonical, checked_path, connection, digest, ensure_root, get_source, validate_locations, writer_lock
from .budget import check_budget

MAX_READ = 32 * 1024 * 1024


def file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with checked_path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def _copy_snapshot(source: Path, destination: Path) -> tuple[str, int]:
    result = hashlib.sha256()
    size = 0
    with source.open('rb') as original, destination.open('xb') as output:
        for chunk in iter(lambda: original.read(1024 * 1024), b''):
            result.update(chunk)
            size += len(chunk)
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    return result.hexdigest(), size


def register_source(root: Path, path: Path, batch_id: str, kind: str) -> LibrarySource:
    validate_locations(root, path)
    with writer_lock(root) as root, connection(root, writable=True) as db:
        return _register_source_in_transaction(root, path, batch_id, kind, db)


def _register_source_in_transaction(root: Path, path: Path, batch_id: str, kind: str, db) -> LibrarySource:
    path = checked_path(path)
    validate_locations(root, path)
    if kind not in ('case_csv', 'law_markdown') or not isinstance(batch_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', batch_id):
        raise ValueError('SOURCE_KIND_OR_BATCH_INVALID')
    if not path.is_file() or path.suffix.lower() != ('.csv' if kind == 'case_csv' else '.md'):
        raise ValueError('SOURCE_FORMAT_INVALID')
    before = path.stat()
    check_budget(root, additional_bytes=before.st_size)
    temporary = root / ('.incoming-' + uuid4().hex)
    try:
        sha256, size = _copy_snapshot(path, temporary)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or size != before.st_size:
            raise ValueError('SOURCE_CHANGED')
        if file_hash(temporary) != sha256:
            raise ValueError('SNAPSHOT_HASH_MISMATCH')
        destination = checked_path(root / 'assets' / sha256 / 'original')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.stat().st_size != size or file_hash(destination) != sha256:
                raise ValueError('ASSET_HASH_MISMATCH')
        else:
            temporary.rename(destination)
        source_id = digest(canonical(['qx-library-source-v1', batch_id, kind, sha256]).encode('utf-8'))
        previous = db.execute('SELECT source_json FROM sources WHERE source_id=?', (source_id,)).fetchone()
        if previous:
            item = LibrarySource.model_validate_json(previous[0])
            aliases = tuple(dict.fromkeys((*item.aliases, str(path))))
            item = item.model_copy(update={'aliases': aliases})
        else:
            item = LibrarySource(source_id=source_id, batch_id=batch_id, sha256=sha256, size=size,
                                 asset_key=sha256 + '/original', kind=kind, aliases=(str(path),),
                                 registered_at=datetime.now(timezone.utc))
        db.execute('INSERT INTO sources VALUES(?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET source_json=excluded.source_json',
                   (source_id, sha256, batch_id, kind, item.model_dump_json()))
        return item
    finally:
        if temporary.exists():
            temporary.unlink()


def asset_path(root: Path, source: LibrarySource) -> Path:
    root = ensure_root(root)
    source = LibrarySource.model_validate(source.model_dump(mode='json'))
    path = checked_path(root / 'assets' / source.asset_key)
    if not path.is_file() or path.stat().st_size != source.size:
        raise ValueError('ASSET_SIZE_MISMATCH')
    return path


def read_asset(root: Path, source_id: str, start: int, end: int) -> bytes:
    source = get_source(root, source_id)
    if type(start) is not int or type(end) is not int or not 0 <= start <= end <= source.size or end - start > MAX_READ:
        raise ValueError('ASSET_RANGE_INVALID')
    path = asset_path(root, source)
    with path.open('rb') as stream:
        stream.seek(start)
        raw = stream.read(end - start)
    if len(raw) != end - start:
        raise ValueError('ASSET_READ_INCOMPLETE')
    if start == 0 and end == source.size and digest(raw) != source.sha256:
        raise ValueError('ASSET_HASH_MISMATCH')
    return raw
