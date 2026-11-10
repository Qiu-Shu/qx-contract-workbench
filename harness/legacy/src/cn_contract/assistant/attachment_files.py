"""Bounded local bytes; no SQLite lock spans upload reads or DOCX parsing."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory

from ..ops.backup import checked_file, checked_root
from ..ops.file_paths import filesystem_path
from ..security import ServiceError


@contextmanager
def stage(stream, database):
    root = checked_root(database.storage_root)
    limit = database.settings.upload_max_file_mib * 1024**2
    # This owned staging directory is on the workspace volume, outside protected.
    with TemporaryDirectory(prefix='.assistant-upload-', dir=filesystem_path(root.parent)) as temporary:
        path = Path(temporary)/'upload.bin'
        total, checksum = 0, hashlib.sha256()
        with path.open('xb') as output:
            while True:
                chunk = stream.read(min(65536, limit-total+1))
                if not isinstance(chunk, bytes):
                    raise ServiceError('FILE_UNSUPPORTED', 400)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ServiceError('FILE_LIMIT', 413)
                checksum.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if not total:
            raise ServiceError('FILE_UNSUPPORTED', 400)
        yield path, total, checksum.hexdigest()


def publish(staged, root, relative):
    root = filesystem_path(checked_root(root))
    parent = root/relative.parent
    checked_root(parent.parent, create=True)
    parent.mkdir()  # UUID-owned exclusive destination, never replace an original.
    target = parent/relative.name
    try:
        os.rename(staged, target)
        target.chmod(stat.S_IREAD)
    except BaseException:
        if target.exists():
            remove_uncommitted(target, root)
        elif not any(parent.iterdir()):
            parent.rmdir()
        raise
    return target


def remove_uncommitted(target, root):
    # Only a just-created, independently linked file whose DB receipt is absent.
    checked_file(target, root)
    target.chmod(stat.S_IREAD | stat.S_IWRITE)
    target.unlink()
    target.parent.rmdir()


def read_checked(row, database):
    root = checked_root(database.storage_root)
    expected = f"assistant/{row['conversation_id']}/{row['id']}/original.bin"
    if row['storage_ref'] != expected:
        raise ServiceError('VERSION_CONFLICT', 409)
    try:
        raw = checked_file(root/expected, root)
    except (OSError, ValueError):
        raise ServiceError('VERSION_CONFLICT', 409) from None
    if len(raw) != row['byte_size'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ServiceError('VERSION_CONFLICT', 409)
    return raw
