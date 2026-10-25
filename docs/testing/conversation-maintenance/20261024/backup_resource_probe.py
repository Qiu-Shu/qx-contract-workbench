"""Synthetic restore publication probes; no live data, no model network."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sqlite3.dbapi2
import subprocess

import pytest

from cn_contract.ops import workspace_backup
from cn_contract.web import local_server
from tests.integration.test_workspace_backup import PASSPHRASE, source


@pytest.mark.parametrize('publish_fails', [False, True])
def test_final_publish_has_no_owned_open_resources(source, tmp_path, monkeypatch, publish_fails):
    parent, root, *_ = source
    archive = tmp_path / 'resource-probe.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=parent)
    original_hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in root.rglob('*') if p.is_file()}
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    original_connect = sqlite3.connect
    original_lock = local_server._worker_lock
    original_rename = Path.rename
    connections = []
    held_locks = []
    publish_calls = []

    class TrackedConnection(sqlite3.Connection):
        def close(self):
            try:
                return super().close()
            finally:
                self.probe_closed = True

    def connect(*args, **kwargs):
        assert 'factory' not in kwargs
        db = original_connect(*args, factory=TrackedConnection, **kwargs)
        db.probe_closed = False
        db.probe_path = str(args[0] if args else kwargs.get('database'))
        connections.append(db)
        return db

    @contextmanager
    def worker_lock(path):
        with original_lock(path):
            held_locks.append(str(path))
            try:
                yield
            finally:
                held_locks.remove(str(path))

    def rename(path, target):
        if path.name == 'workspace' and path.parent.name.startswith('.qx-restore-'):
            assert connections and all(db.probe_closed for db in connections)
            assert held_locks == []
            # macOS process handle inventory only supports this host's lifetime check.
            result = subprocess.run(['/usr/sbin/lsof', '-a', '-p', str(os.getpid()), '-Fn'],
                                    capture_output=True, text=True, check=False)
            assert result.returncode == 0, result.stderr
            staged_handles = [line[1:] for line in result.stdout.splitlines()
                              if line.startswith('n') and str(path) in line[1:]]
            assert staged_handles == []
            publish_calls.append({'connections_closed': len(connections),
                                  'worker_locks_held': len(held_locks),
                                  'stage_handles': len(staged_handles),
                                  'injected_failure': publish_fails})
            if publish_fails:
                raise PermissionError(13, 'synthetic final publication denial')
        return original_rename(path, target)

    monkeypatch.setattr(sqlite3, 'connect', connect)
    monkeypatch.setattr(sqlite3.dbapi2, 'connect', connect)
    monkeypatch.setattr(local_server, '_worker_lock', worker_lock)
    monkeypatch.setattr(Path, 'rename', rename)
    restore_parent = parent / 'resource-probe-restores'
    sentinel = parent / 'unrelated.txt'
    sentinel.write_bytes(b'synthetic unrelated file')
    if publish_fails:
        with pytest.raises(PermissionError, match='synthetic final publication denial'):
            workspace_backup.restore_workspace_backup(archive, restore_parent, PASSPHRASE)
        assert list(restore_parent.iterdir()) == []
    else:
        restored = workspace_backup.restore_workspace_backup(archive, restore_parent, PASSPHRASE)
        assert Path(restored['restored_root']).is_dir() and restored['quarantined']
        assert [p.name for p in restore_parent.iterdir()] == [Path(restored['restored_root']).name]
    assert len(publish_calls) == 1
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_hash
    assert {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()} == original_hashes
    assert sentinel.read_bytes() == b'synthetic unrelated file'
    print(json.dumps(publish_calls[0], sort_keys=True))
