import hashlib
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid


@unittest.skipUnless(os.name == 'nt', 'Windows file sharing and ACL boundary')
class SnapshotTests(unittest.TestCase):
    def worker_request(self, request, gbk=False):
        executable=os.environ.get('QX_TEST_EMBEDDED_PYTHON',sys.executable)
        script=str(Path(__file__).with_name('backup_snapshot.py'))
        args=[executable,'-X','utf8=0',script]
        if gbk:
            args=[executable,'-X','utf8=0','-c',"import runpy,sys;sys.stdin.reconfigure(encoding='gbk');runpy.run_path(sys.argv[1],run_name='__main__')",script]
        env={k:v for k,v in os.environ.items() if k.upper() not in ('PYTHONIOENCODING','PYTHONUTF8')}
        return subprocess.run(args,input=json.dumps(request,ensure_ascii=False).encode('utf-8'),capture_output=True,env=env)

    def test_worker_protocol_is_utf8_even_when_embedded_stdin_defaults_to_gbk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();source=root/'中文来源';source.mkdir()
            document=source/'合同中文.txt';document.write_bytes(b'synthetic')
            plan={'files':[{'path':document.name,'bytes':9,'policy':'protect'}],
                  'scopes':[{'path':document.name,'policy':'protect'}]}
            result=self.worker_request({'action':'create','source':str(source),'destination':str(root/'snapshot'),'plan':plan},gbk=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue(result.stdout.isascii())
            self.assertEqual(json.loads(result.stdout)['sourceRoot'],str(source))
            self.assertEqual((root/'snapshot'/document.name).read_bytes(),b'synthetic')

    def test_embedded_worker_supports_long_internal_paths_without_accepting_device_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path('\\\\?\\'+str(Path(tmp).resolve()))
            root=base/('a'*100)/('b'*100);root.mkdir(parents=True)
            source=root/'source';document=source/'workspace/中文原件.txt';document.parent.mkdir(parents=True)
            document.write_bytes(b'synthetic')
            session=source/'.local/dsh-home/sessions'/('project-'+'x'*80)/'flow-session/session.v3.jsonl'
            session.parent.mkdir(parents=True);session.write_bytes(b'synthetic session')
            database=source/'workspace/.qx-materials/index.sqlite';database.parent.mkdir()
            with contextlib.closing(sqlite3.connect(database)) as db:
                db.execute('CREATE TABLE materials(path TEXT,size INTEGER,sha256 TEXT)')
                db.execute('INSERT INTO materials VALUES(?,?,?)',(document.name,9,hashlib.sha256(b'synthetic').hexdigest()));db.commit()
            self.assertGreater(len(str(database)),300)
            before={p.relative_to(source).as_posix():(p.read_bytes(),p.stat().st_mtime_ns) for p in source.rglob('*') if p.is_file()}
            plan={'files':[{'path':n,'bytes':len(v[0]),'policy':'protect'} for n,v in before.items()],
                  'scopes':[{'path':'workspace','policy':'protect'},{'path':'.local','policy':'protect'}]}
            normal=lambda p:str(p)[4:]
            def action(request):
                result=self.worker_request(request);self.assertEqual(result.returncode,0,result.stdout+result.stderr);return json.loads(result.stdout)
            try:
                from backup_snapshot import readonly_database_uri
                with contextlib.closing(sqlite3.connect(readonly_database_uri(normal(database)),uri=True)) as readonly:
                    with self.assertRaisesRegex(sqlite3.OperationalError,'readonly'):
                        readonly.execute('CREATE TABLE forbidden(value)')
                missing=source/'workspace/.qx-materials/missing.sqlite'
                with self.assertRaises(sqlite3.OperationalError):
                    sqlite3.connect(readonly_database_uri(normal(missing)),uri=True)
                self.assertFalse(missing.exists())
                restored=root/'restored';checked=action({'action':'create','source':normal(source),'destination':normal(restored),'plan':plan})
                self.assertEqual(checked['sourceRoot'],normal(source))
                action({'action':'review','root':normal(restored)})
                copied=root/'copy';action({'action':'copy-verified','root':normal(restored),'destination':normal(copied),'manifestSha256':checked['manifestSha256']})
                self.assertEqual(before,{p.relative_to(source).as_posix():(p.read_bytes(),p.stat().st_mtime_ns) for p in source.rglob('*') if p.is_file()})
                with (restored/'workspace/中文原件.txt').open('r+b'):
                    busy=self.worker_request({'action':'review','root':normal(restored)})
                self.assertEqual(json.loads(busy.stdout)['error'],'BACKUP_SOURCE_BUSY')
                rejected=self.worker_request({'action':'verify','root':str(restored)})
                self.assertEqual(json.loads(rejected.stdout)['error'],'BACKUP_LOCAL_WINDOWS_PATH_REQUIRED')
                (copied/'backup-manifest.json').unlink()
                sealed=action({'action':'seal-prepared','root':normal(copied)})
                receipt={'schema':1,'id':str(uuid.uuid4()),'phase':'prepared','data':normal(copied),'preparedManifestSha256':sealed['preparedManifestSha256']}
                (copied/'.local/restore-activation.json').write_text(json.dumps(receipt),encoding='utf-8')
                self.assertEqual(action({'action':'verify-prepared','root':normal(copied)}),receipt)
                stamp=(copied/'workspace/中文原件.txt').stat().st_mtime_ns
                os.utime(copied/'workspace/中文原件.txt',ns=(stamp+10000000,stamp+10000000))
                changed=self.worker_request({'action':'verify-prepared','root':normal(copied)})
                self.assertEqual(json.loads(changed.stdout)['error'],'BACKUP_PREPARED_CHANGED')
            finally:
                shutil.rmtree(root)

    def test_prepared_receipt_verification_freezes_files_and_rejects_metadata_changes(self):
        import backup_snapshot as worker
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'.local').mkdir();(root/'workspace').mkdir()
            document=root/'workspace/a.txt';document.write_bytes(b'synthetic')
            sealed=worker.seal_prepared(root)
            receipt={'schema':1,'id':str(uuid.uuid4()),'phase':'prepared','data':str(root),
                     'preparedManifestSha256':sealed['preparedManifestSha256']}
            marker=root/worker.ACTIVATION_RECEIPT
            marker.write_text(json.dumps(receipt),encoding='utf-8')
            self.assertEqual(worker.verify_prepared(root),receipt)
            with document.open('r+b'):
                with self.assertRaisesRegex(ValueError,'BACKUP_SOURCE_BUSY'):
                    worker.verify_prepared(root)
            receipt['id']='-'*36;marker.write_text(json.dumps(receipt),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'BACKUP_PREPARED_CHANGED'):
                worker.verify_prepared(root)
            receipt['id']=str(uuid.uuid4());marker.write_text(json.dumps(receipt),encoding='utf-8')
            before=document.stat().st_mtime_ns
            os.utime(document,ns=(before+10000000,before+10000000))
            with self.assertRaisesRegex(ValueError,'BACKUP_PREPARED_CHANGED'):
                worker.verify_prepared(root)
            os.utime(document,ns=(before,before))
            (root/'workspace/extra').mkdir()
            with self.assertRaisesRegex(ValueError,'BACKUP_PREPARED_CHANGED'):
                worker.verify_prepared(root)

    def test_activation_copy_verifies_and_preserves_the_reviewed_original(self):
        import backup_snapshot as worker
        self.assertTrue(callable(getattr(worker, 'copy_verified_snapshot', None)), 'verified activation copy is missing')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,plan=self.fixture(root)
            restored=root/'restored';checked=worker.create_snapshot(source,restored,plan)
            before={p.relative_to(restored).as_posix():(p.read_bytes(),p.stat().st_mtime_ns) for p in restored.rglob('*') if p.is_file()}
            copied=worker.copy_verified_snapshot(restored,root/'activation',checked['manifestSha256'])
            self.assertEqual(copied['manifestSha256'],checked['manifestSha256'])
            self.assertEqual(worker.verify_snapshot(root/'activation')['fileCount'],1)
            self.assertEqual(before,{p.relative_to(restored).as_posix():(p.read_bytes(),p.stat().st_mtime_ns) for p in restored.rglob('*') if p.is_file()})
            with self.assertRaisesRegex(ValueError,'BACKUP_TARGET_EXISTS'):
                worker.copy_verified_snapshot(restored,root/'activation',checked['manifestSha256'])
            with self.assertRaisesRegex(ValueError,'BACKUP_REVIEW_STALE'):
                worker.copy_verified_snapshot(restored,root/'stale','0'*64)
            self.assertFalse((root/'stale').exists())
            with (restored/'workspace/a.txt').open('r+b'):
                with self.assertRaisesRegex(ValueError,'BACKUP_SOURCE_BUSY'):
                    worker.copy_verified_snapshot(restored,root/'busy',checked['manifestSha256'])
            self.assertFalse((root/'busy').exists())

    def test_activation_copy_refuses_overlap_and_corruption_before_publication(self):
        import backup_snapshot as worker
        self.assertTrue(callable(getattr(worker, 'copy_verified_snapshot', None)), 'verified activation copy is missing')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,plan=self.fixture(root)
            restored=root/'restored';checked=worker.create_snapshot(source,restored,plan)
            for target in [restored/'child',source/'child',root]:
                with self.assertRaisesRegex(ValueError,'BACKUP_OVERLAPPING_PATHS'):
                    worker.copy_verified_snapshot(restored,target,checked['manifestSha256'])
            (restored/'workspace/a.txt').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'BACKUP_FILE_HASH_MISMATCH'):
                worker.copy_verified_snapshot(restored,root/'invalid',checked['manifestSha256'])
            self.assertFalse((root/'invalid').exists())

    def test_original_drive_can_be_offline_while_the_reviewed_restore_is_copied(self):
        import backup_snapshot as worker
        drive=next((letter for letter in 'ZYXWV' if not Path(letter+':/').exists()),None)
        if drive is None:self.skipTest('no unavailable drive for the historical-prefix fixture')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();source,plan=self.fixture(root)
            restored=root/'restored';worker.create_snapshot(source,restored,plan)
            manifest_path=restored/'backup-manifest.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['sourceRoot']=drive+':\\previous-computer\\data'
            manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
            checked=worker.verify_snapshot(restored)
            self.assertEqual(worker.review_snapshot(restored)['sourceRoot'],manifest['sourceRoot'])
            copied=worker.copy_verified_snapshot(restored,root/'copy',checked['manifestSha256'])
            self.assertEqual(copied['sourceRoot'],manifest['sourceRoot'])
            self.assertEqual((root/'copy/workspace/a.txt').read_bytes(),b'synthetic')

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

    def test_empty_directories_are_verified_and_older_manifests_still_read(self):
        from backup_snapshot import create_snapshot,verify_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,plan=self.fixture(root)
            (source/'workspace/empty/nested').mkdir(parents=True)
            destination=root/'snapshot';create_snapshot(source,destination,plan)
            self.assertTrue((destination/'workspace/empty/nested').is_dir())
            (destination/'workspace/empty/nested').rmdir()
            with self.assertRaisesRegex(ValueError,'BACKUP_DIRECTORY_SET_MISMATCH'):
                verify_snapshot(destination)
            manifest_path=destination/'backup-manifest.json'
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'));del manifest['directories']
            manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
            self.assertEqual(verify_snapshot(destination)['fileCount'],1)


if __name__ == '__main__':
    unittest.main()
