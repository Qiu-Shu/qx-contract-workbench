"""Synthetic-only restic experiment. No caller-supplied source or restore paths."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[1]
LOCAL = HARNESS / '.local' / 'audit-followups'
VERSION = '0.19.1'
ARCHIVE = 'restic_0.19.1_windows_amd64.zip'
ARCHIVE_SHA256 = 'da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d'
ARCHIVE_BYTES = 11237567
DOWNLOAD = f'https://github.com/restic/restic/releases/download/v{VERSION}/{ARCHIVE}'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def no_links(path):
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                    'Link or Windows reparse point rejected')


def prepare_restic(download):
    no_links(LOCAL)
    downloads = LOCAL / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / ARCHIVE
    no_links(archive)
    if not archive.exists():
        require(download, 'Pass --download to fetch the pinned official 11.2 MB release')
        request = urllib.request.Request(DOWNLOAD, headers={'User-Agent': 'qx-synthetic-audit-experiment'})
        with urllib.request.urlopen(request, timeout=45) as response, archive.open('xb') as output:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                require(total <= ARCHIVE_BYTES, 'Download exceeds pinned release size')
                output.write(block)
    require(archive.stat().st_size == ARCHIVE_BYTES and sha(archive) == ARCHIVE_SHA256,
            'Official archive checksum/size mismatch; do not execute')
    binary = downloads / f'restic_{VERSION}_windows_amd64.exe'
    no_links(binary)
    with zipfile.ZipFile(archive) as package:
        member = package.getinfo(binary.name)
        require(member.file_size < 50 * 1024 * 1024, 'Unexpected expanded binary size')
        data = package.read(member)
    binary_hash = hashlib.sha256(data).hexdigest()
    if binary.exists():
        require(sha(binary) == binary_hash, 'Cached binary differs from verified archive')
    else:
        with binary.open('xb') as output:
            output.write(data)
    return binary, binary_hash


def files(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if stat.S_ISREG(p.stat().st_mode)}


def restore_guard(target, run, source, stage, repository):
    no_links(target)
    target = target.resolve()
    require(target.is_relative_to(run.resolve()) and target != run.resolve(), 'Restore outside experiment run rejected')
    for protected in (source, stage, repository):
        protected = protected.resolve()
        require(not target.is_relative_to(protected) and not protected.is_relative_to(target),
                'Restore overlaps protected directory')
    require(not target.exists(), 'Restore target must be a new directory')


def run_experiment(download=False):
    started = time.monotonic()
    binary, binary_hash = prepare_restic(download)
    runs = LOCAL / 'runs'
    no_links(runs)
    runs.mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='backup-', dir=runs))
    source, stage, repository = (run / name for name in ('synthetic-source', 'snapshot', 'repository'))
    for path in (source / 'inbox', source / 'drafts', source / 'credentials', stage):
        path.mkdir(parents=True)
    originals = {'inbox/contract.txt': '完全虚构样本：甲方北辰测试有限公司，金额 12000 元。\n',
                 'drafts/review.md': '# 合成审查意见\n仅供备份恢复实验。\n'}
    for name, value in originals.items():
        (source / name).write_text(value, encoding='utf-8')
    (source / 'credentials' / '.env').write_text('FAKE_API_KEY=synthetic-never-valid\n', encoding='utf-8')
    (source / 'credentials' / 'wechat-session.json').write_text('{"synthetic":true}', encoding='utf-8')
    password = run / 'ephemeral-password.txt'
    password.write_text(secrets.token_urlsafe(48), encoding='ascii')
    wrong = run / 'wrong-password.txt'
    wrong.write_text(secrets.token_urlsafe(48), encoding='ascii')
    events, checks = [], []
    report = {'schema': 1, 'synthetic_only': True, 'started_at': datetime.now(timezone.utc).isoformat(),
              'restic_version': VERSION, 'archive_sha256': ARCHIVE_SHA256, 'binary_sha256': binary_hash,
              'commands': events, 'checks': checks, 'status': 'failed'}

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        require(condition, name)

    def command(*args, password_path=password, expected=0):
        env = {k: v for k, v in os.environ.items() if not k.startswith('RESTIC_')}
        # The password is never an argument, log field, or backed-up file.
        env.update(RESTIC_PASSWORD_FILE=str(password_path), GOMAXPROCS='2')
        argv = [str(binary), '--repo', str(repository), '--no-cache', *args]
        begin = time.monotonic()
        result = subprocess.run(argv, cwd=run, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=120)
        event = {'args': [str(x).replace(str(run), '<run>').replace(str(binary), '<restic>') for x in argv],
                 'password': 'wrong' if password_path == wrong else 'ephemeral',
                 'exit_code': result.returncode, 'seconds': round(time.monotonic() - begin, 3),
                 'stdout': result.stdout.replace(str(run), '<run>'),
                 'stderr': result.stderr.replace(str(run), '<run>')}
        events.append(event)
        require(result.returncode == expected, f'Unexpected exit {result.returncode} for {args[0]}: {result.stderr}')
        return result

    try:
        version = command('version')
        check('verified_binary_reports_pinned_version', version.stdout.startswith(f'restic {VERSION} '))
        with closing(sqlite3.connect(source / 'business.sqlite')) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, path TEXT, sha256 TEXT)')
            writer.commit()
            writer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            expected_rows = [(i, 'inbox/contract.txt', sha(source / 'inbox/contract.txt')) for i in range(1, 51)]
            writer.executemany('INSERT INTO records VALUES(?,?,?)', expected_rows)
            writer.commit()
            check('committed_rows_exist_in_live_WAL', (source / 'business.sqlite-wal').stat().st_size > 0)
            writer.execute('INSERT INTO records VALUES(999,?,?)', ('uncommitted', 'must-not-appear'))
            # Hold all file writers stopped; read the committed DB view with SQLite's backup API.
            with closing(sqlite3.connect(source / 'business.sqlite')) as reader, closing(sqlite3.connect(stage / 'business.sqlite')) as output:
                reader.backup(output)
                check('snapshot_excludes_uncommitted_transaction', output.execute('SELECT * FROM records ORDER BY id').fetchall() == expected_rows)
            writer.rollback()
        for name in originals:
            (stage / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, stage / name)
        with closing(sqlite3.connect(stage / 'business.sqlite')) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            check('snapshot_database_integrity', db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
        manifest = {'synthetic_only': True, 'rows': len(expected_rows), 'files': files(stage),
                    'excluded': ['credentials/', 'raw WAL/SHM', 'ephemeral passwords'],
                    'consistency': 'immutable files; stopped file writers; SQLite backup API with open uncommitted transaction'}
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        expected = files(stage)
        source_before = files(source)
        check('snapshot_allowlist_excludes_credentials_and_WAL', set(expected) == {'business.sqlite', 'manifest.json', *originals})
        command('init', '--repository-version', '2')
        backup = command('backup', stage.name, '--host', 'synthetic-audit-host', '--tag', 'synthetic-only', '--json')
        summary = next(json.loads(line) for line in backup.stdout.splitlines() if json.loads(line).get('message_type') == 'summary')
        snapshot = summary['snapshot_id']
        report.update(snapshot_id=snapshot, backed_up_files=summary['total_files_processed'], backed_up_bytes=summary['total_bytes_processed'])
        command('check', '--read-data')
        command('snapshots', '--json', password_path=wrong, expected=12)
        check('wrong_password_rejected', events[-1]['exit_code'] == 12)
        # A missing input must be visible as a nonzero result (restic exit 3).
        command('backup', stage.name, 'missing-source', '--host', 'synthetic-audit-host', expected=3)
        check('missing_source_is_not_silent_success', events[-1]['exit_code'] == 3)
        occupied = run / 'occupied'
        occupied.mkdir()
        sentinel = occupied / 'keep.txt'
        sentinel.write_text('do-not-overwrite', encoding='ascii')
        empty = run / 'existing-empty'
        empty.mkdir()
        for name, target in [('source', source), ('source-child', source / 'restore'), ('stage', stage),
                             ('repository', repository), ('ancestor', run), ('outside', run.parent / 'escape'),
                             ('nonempty', occupied), ('existing-empty', empty)]:
            try:
                restore_guard(target, run, source, stage, repository)
            except RuntimeError:
                check('restore_guard_' + name, True)
            else:
                check('restore_guard_' + name, False)
        check('existing_target_preserved', sentinel.read_text(encoding='ascii') == 'do-not-overwrite')
        restored = run / 'restored-new'
        restore_guard(restored, run, source, stage, repository)
        restored.mkdir()  # Exclusive creation reserves this experiment-owned destination.
        command('restore', snapshot, '--target', str(restored), '--overwrite', 'never', '--verify')
        manifests = list(restored.rglob('manifest.json'))
        check('exactly_one_restored_manifest', len(manifests) == 1)
        restored_root = manifests[0].parent
        check('restored_file_set_and_sha256_match', files(restored_root) == expected)
        with closing(sqlite3.connect(restored_root / 'business.sqlite')) as db:
            check('restored_database_integrity', db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
            rows = db.execute('SELECT * FROM records ORDER BY id').fetchall()
            check('restored_database_rows_and_file_links_match', rows == expected_rows and all(sha(restored_root / row[1]) == row[2] for row in rows))
        check('source_remains_unchanged', files(source) == source_before)
        # Exercise the verifier against actual altered and missing restored bytes.
        victim = restored_root / 'drafts' / 'review.md'
        saved = victim.read_bytes()
        victim.write_bytes(saved + b'corruption')
        check('verifier_detects_corruption', files(restored_root) != expected)
        victim.write_bytes(saved)
        victim.unlink()
        check('verifier_detects_missing_file', files(restored_root) != expected)
        victim.write_bytes(saved)
        check('final_restored_hashes_match', files(restored_root) == expected)
        report.update(status='passed', manifest=manifest, restored_files=len(expected), database_rows=len(rows))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        password.unlink(missing_ok=True)
        wrong.unlink(missing_ok=True)
        report['password_files_removed'] = not password.exists() and not wrong.exists()
        report['seconds'] = round(time.monotonic() - started, 3)
        report['repository_bytes'] = sum(p.stat().st_size for p in repository.rglob('*') if p.is_file())
        report['check_count'] = len(checks)
        (run / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': report['status'], 'checks': len(checks), 'result': str(run / 'result.json')}, ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Fetch only the pinned official 11.2 MB archive')
    run_experiment(parser.parse_args().download)
