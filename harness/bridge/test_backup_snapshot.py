import hashlib
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == 'nt', 'Windows file sharing and ACL boundary')
class SnapshotTests(unittest.TestCase):
    def test_snapshot_captures_committed_wal_without_touching_sources(self):
        from backup_snapshot import create_snapshot, verify_snapshot
        with tempfile.TemporaryDirectory(prefix='qx-snapshot-') as tmp:
            root = Path(tmp); source = root / 'source'; source.mkdir()
            db = source / 'workspace/.qx-materials/index.sqlite'; db.parent.mkdir(parents=True)
            original = source / 'workspace/inbox/original.txt'; original.parent.mkdir()
            original.write_bytes(b'synthetic-original')
            # Simulated crashed writer leaves committed WAL; its uncommitted row must not survive.
            script = '''import sqlite3,sys,os
c=sqlite3.connect(sys.argv[1]);c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA wal_autocheckpoint=0')
c.execute('CREATE TABLE materials(path TEXT,size INTEGER,sha256 TEXT)');c.commit();c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
c.execute('INSERT INTO materials VALUES(?,?,?)',('inbox/original.txt',18,sys.argv[2]));c.commit()
c.execute('INSERT INTO materials VALUES(?,?,?)',('uncommitted',0,'bad'));os._exit(0)
'''
            subprocess.run([sys.executable, '-c', script, str(db), hashlib.sha256(original.read_bytes()).hexdigest()], check=True)
            self.assertGreater(Path(str(db)+'-wal').stat().st_size, 0)
            names = sorted(p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file())
            before = {n: (source/n).read_bytes() for n in names}
            plan = {'files': [{'path': n, 'bytes': len(before[n]), 'policy': 'protect'} for n in names],
                    'scopes': [{'path': 'workspace', 'policy': 'protect'}]}
            destination = root / 'snapshot'
            result = create_snapshot(source, destination, plan)
            self.assertEqual(result['databaseCount'], 1)
            with contextlib.closing(sqlite3.connect(destination / 'workspace/.qx-materials/index.sqlite')) as restored:
                self.assertEqual(restored.execute('SELECT path FROM materials').fetchall(), [('inbox/original.txt',)])
            self.assertFalse(list(destination.rglob('*-wal')))
            self.assertEqual({n: (source/n).read_bytes() for n in names}, before)
            self.assertEqual(verify_snapshot(destination)['fileCount'], 2)

    def fixture(self, root):
        source = root/'source'; (source/'workspace').mkdir(parents=True)
        (source/'workspace/a.txt').write_bytes(b'synthetic')
        plan = {'files': [{'path': 'workspace/a.txt', 'bytes': 9, 'policy': 'protect'}],
                'scopes': [{'path': 'workspace', 'policy': 'protect'}]}
        return source, plan

    def test_rejects_writer_and_releases_handles(self):
        from backup_snapshot import create_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, plan = self.fixture(root)
            with (source/'workspace/a.txt').open('r+b'):
                with self.assertRaisesRegex(ValueError, 'BACKUP_SOURCE_BUSY'):
                    create_snapshot(source, root/'snapshot', plan)
            self.assertFalse((root/'snapshot').exists())
            create_snapshot(source, root/'snapshot', plan)
            (source/'workspace/a.txt').write_bytes(b'allowed after release')

    def test_exact_manifest_and_private_acl(self):
        from backup_snapshot import create_snapshot, verify_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, plan = self.fixture(root)
            destination = root/'snapshot'; create_snapshot(source, destination, plan)
            command = "$ErrorActionPreference='Stop'; $a=[System.IO.Directory]::GetAccessControl($env:QX_ACL_TEST); [pscustomobject]@{protected=$a.AreAccessRulesProtected;rules=@($a.Access | ForEach-Object {$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value});self=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value}|ConvertTo-Json -Compress"
            acl = json.loads(subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', command],
                env={**os.environ, 'QX_ACL_TEST': str(destination)}, text=True))
            self.assertTrue(acl['protected']); self.assertEqual(acl['rules'], [acl['self']])
            (destination/'workspace/extra').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'BACKUP_FILE_SET_MISMATCH'):
                verify_snapshot(destination)
            (destination/'workspace/extra').unlink()
            (destination/'workspace/a.txt').write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError, 'BACKUP_FILE_HASH_MISMATCH'):
                verify_snapshot(destination)

    def test_invalid_database_cleans_only_new_destination(self):
        from backup_snapshot import create_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, plan = self.fixture(root)
            bad = source/'workspace/bad.sqlite'; bad.write_bytes(b'broken')
            plan['files'].append({'path': 'workspace/bad.sqlite', 'bytes': 6, 'policy': 'protect'})
            with self.assertRaisesRegex(ValueError, 'BACKUP_DATABASE_INVALID'):
                create_snapshot(source, root/'snapshot', plan)
            self.assertFalse((root/'snapshot').exists()); self.assertTrue(bad.exists())
            (root/'snapshot').mkdir(); (root/'snapshot/keep').write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError, 'BACKUP_DIRECTORY_CREATE_FAILED'):
                create_snapshot(source, root/'snapshot', plan)
            self.assertEqual((root/'snapshot/keep').read_bytes(), b'keep')

    def test_rejects_inventory_change_and_hardlink(self):
        from backup_snapshot import create_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, plan = self.fixture(root)
            (source/'workspace/new').write_bytes(b'new')
            with self.assertRaisesRegex(ValueError, 'BACKUP_SOURCE_CHANGED'):
                create_snapshot(source, root/'snapshot', plan)
            (source/'workspace/new').unlink()
            os.link(source/'workspace/a.txt', root/'link')
            with self.assertRaisesRegex(ValueError, 'BACKUP_LINKED_PATH'):
                create_snapshot(source, root/'snapshot', plan)

    def test_preserves_material_timestamp_used_by_current(self):
        from backup_snapshot import create_snapshot
        from store import MaterialStore
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source,plan=self.fixture(root)
            original=source/'workspace/a.txt'
            os.utime(original, ns=(1230000000000000000, 1230000000000000000))
            store=MaterialStore(source/'workspace');store.register(original)
            plan['files']=[{'path':p.relative_to(source).as_posix(),'bytes':p.stat().st_size,'policy':'protect'} for p in source.rglob('*') if p.is_file()]
            create_snapshot(source, root/'snapshot', plan)
            self.assertEqual((root/'snapshot/workspace/a.txt').stat().st_mtime_ns, original.stat().st_mtime_ns)
            restored=MaterialStore(root/'snapshot/workspace')
            with restored.db() as db:
                self.assertEqual(restored.current('a.txt',db)[2]['sha256'],hashlib.sha256(b'synthetic').hexdigest())

    def test_reviewed_private_copy_must_match_its_record(self):
        from backup_snapshot import create_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,plan=self.fixture(root)
            vault=source/'.qx-private/uploads'; document=vault/'documents/d1';document.mkdir(parents=True)
            (vault/'safe').mkdir();(vault/'safe/reviewed.txt').write_bytes(b'changed')
            (document/'reviewed-1.json').write_text(json.dumps({'safe_file':'safe/reviewed.txt','sha256':hashlib.sha256(b'expected').hexdigest()}))
            plan['scopes'].append({'path':'.qx-private','policy':'protect'})
            plan['files']=[{'path':p.relative_to(source).as_posix(),'bytes':p.stat().st_size,'policy':'protect'} for p in source.rglob('*') if p.is_file()]
            with self.assertRaisesRegex(ValueError,'BACKUP_PRIVATE_REFERENCE_INVALID'):
                create_snapshot(source,root/'snapshot',plan)
            self.assertFalse((root/'snapshot').exists())


if __name__ == '__main__':
    unittest.main()
