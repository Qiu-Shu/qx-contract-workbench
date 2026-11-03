"""Backup safety checks use only isolated synthetic libraries."""
import importlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import warnings
import zipfile

from knowledge import KnowledgeStore


class KnowledgeTransferTests(unittest.TestCase):
    def setUp(self):
        try:
            self.transfer = importlib.import_module('knowledge_transfer')
        except ModuleNotFoundError:
            self.fail('knowledge_transfer backup/restore implementation is missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = KnowledgeStore(self.root / 'source')
        self.target = KnowledgeStore(self.root / 'target')
        self.archive = self.root / 'backup.zip'

    def document(self, kb, identifier=None, text='原始内容', title='测试资料', archived=False):
        identifier = identifier or str(uuid4())
        source = kb.store.root / 'documents' / identifier / '原件.txt'
        source.parent.mkdir(parents=True)
        source.write_text(text, encoding='utf-8')
        kb.register(identifier, title, '测试分类')
        key = source.relative_to(kb.store.root).as_posix()
        with kb.store.db() as db:
            db.execute("UPDATE materials SET status='ready',page_count=2,warnings='[\"合成资料\"]' WHERE path=?", (key,))
            db.executemany('INSERT INTO chunks VALUES(?,?,?,?,?)', [
                (key, 3, 1, '第1页第4段', text), (key, 9, 2, '第2页第1段', '后续段落')])
        kb.set_state(identifier, 'ready')
        if archived:
            kb.archive(identifier)
        return identifier

    def rewrite(self, mutate):
        with zipfile.ZipFile(self.archive) as source:
            entries = [(item, source.read(item)) for item in source.infolist()]
        entries = mutate(entries)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.archive, 'w') as target:
                for item, data in entries:
                    target.writestr(item, data)

    def assert_empty_target(self):
        self.assertEqual(self.target.list()['total'], 0)
        documents = self.target.store.root / 'documents'
        self.assertFalse(documents.exists() and list(documents.iterdir()))

    def test_roundtrip_keeps_original_citations_archived_and_index(self):
        identifier = self.document(self.source)
        archived = self.document(self.source, text='归档原件', archived=True)
        citation = self.source.read(identifier)['chunks'][0]['citation']
        report = self.transfer.export_backup(self.source, self.archive)
        self.assertEqual(report['documents'], 2)
        result = self.transfer.restore_backup(self.target, self.archive)
        self.assertEqual((result['imported'], result['skipped'], result['chunks']), (2, 0, 4))
        self.assertEqual(self.target.citation(citation)['text'], '原始内容')
        self.assertEqual(self.target.citation(citation)['location'], '第1页第4段')
        self.assertEqual(self.target.list(archived=True)['documents'][0]['id'], archived)
        self.assertEqual(Path(self.target.source(archived)['path']).read_text(encoding='utf-8'), '归档原件')
        self.assertEqual(len(self.target.search('原始内容')['matches']), 1)

    def test_same_uuid_and_sha_skips_preserving_local_metadata(self):
        identifier = self.document(self.source)
        self.document(self.target, identifier, title='保留本地名称', archived=True)
        self.transfer.export_backup(self.source, self.archive)
        result = self.transfer.restore_backup(self.target, self.archive)
        self.assertEqual((result['imported'], result['skipped']), (0, 1))
        self.assertEqual(self.target.list(archived=True)['documents'][0]['title'], '保留本地名称')

    def test_uuid_conflict_rejects_entire_import_before_new_documents(self):
        self.document(self.source)
        identifier = self.document(self.source)
        self.document(self.target, identifier, text='本地不同版本')
        self.transfer.export_backup(self.source, self.archive)
        with self.assertRaisesRegex(ValueError, '冲突'):
            self.transfer.restore_backup(self.target, self.archive)
        self.assertEqual(self.target.list()['total'], 1)
        self.assertEqual(Path(self.target.source(identifier)['path']).read_text(encoding='utf-8'), '本地不同版本')

    def test_tampered_original_rejects_without_partial_import(self):
        self.document(self.source)
        self.transfer.export_backup(self.source, self.archive)
        self.rewrite(lambda rows: [(item, b'tampered' if item.filename.startswith('originals/') else data) for item, data in rows])
        with self.assertRaises(ValueError):
            self.transfer.restore_backup(self.target, self.archive)
        self.assert_empty_target()

    def test_rejects_traversal_absolute_windows_aliases_and_extra_entries(self):
        self.document(self.source)
        for name in ['../escape.txt', '/absolute.txt', 'C:/escape.txt', 'originals\\escape.txt',
                     'originals/../escape.txt', 'originals/file.txt:stream', 'manifest.json.', 'extra.sqlite']:
            with self.subTest(name=name):
                if self.archive.exists():
                    self.archive.unlink()
                self.transfer.export_backup(self.source, self.archive)
                self.rewrite(lambda rows: rows + [(name, b'x')])
                with self.assertRaises(ValueError):
                    self.transfer.restore_backup(self.target, self.archive)
                self.assert_empty_target()
                self.assertFalse((self.root / 'escape.txt').exists())

    def test_duplicate_zip_member_and_symlink_are_rejected(self):
        self.document(self.source)
        self.transfer.export_backup(self.source, self.archive)
        self.rewrite(lambda rows: rows + [rows[0]])
        with self.assertRaises(ValueError):
            self.transfer.restore_backup(self.target, self.archive)
        self.archive.unlink()
        self.transfer.export_backup(self.source, self.archive)
        def symlink(rows):
            for item, _ in rows:
                if item.filename.startswith('originals/'):
                    item.create_system = 3
                    item.external_attr = (stat.S_IFLNK | 0o777) << 16
            return rows
        self.rewrite(symlink)
        with self.assertRaises(ValueError):
            self.transfer.restore_backup(self.target, self.archive)
        self.assert_empty_target()

    def test_size_limit_is_checked_before_import(self):
        self.document(self.source)
        self.transfer.export_backup(self.source, self.archive)
        with patch.object(self.transfer, 'MAX_FILE_BYTES', 2):
            with self.assertRaisesRegex(ValueError, '上限'):
                self.transfer.restore_backup(self.target, self.archive)
        self.assert_empty_target()

    def test_archive_file_size_limit_rejects_before_zip_parsing(self):
        self.archive.write_bytes(b'not a zip, larger than the permitted archive')
        with patch.object(self.transfer, 'MAX_ARCHIVE_BYTES', 2, create=True):
            with self.assertRaisesRegex(ValueError, '上限'):
                self.transfer.restore_backup(self.target, self.archive)
        self.assert_empty_target()

    def test_central_directory_count_is_bounded_before_zip_parsing(self):
        self.document(self.source)
        self.transfer.export_backup(self.source, self.archive)
        data = bytearray(self.archive.read_bytes())
        end = data.rfind(b'PK\x05\x06')
        struct.pack_into('<HH', data, end + 8, 60000, 60000)
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(ValueError, '上限'):
            self.transfer.restore_backup(self.target, self.archive)
        self.assert_empty_target()

    def test_existing_unregistered_directory_is_preserved(self):
        identifier = self.document(self.source)
        directory = self.target.store.root / 'documents' / identifier
        directory.mkdir(parents=True)
        (directory / 'keep.txt').write_text('preserve')
        self.transfer.export_backup(self.source, self.archive)
        with self.assertRaisesRegex(ValueError, '冲突'):
            self.transfer.restore_backup(self.target, self.archive)
        self.assertEqual((directory / 'keep.txt').read_text(), 'preserve')
        self.assertEqual(self.target.list()['total'], 0)

    def test_existing_original_hash_is_checked_even_with_unchanged_stat(self):
        identifier = self.document(self.source, text='AAA')
        self.document(self.target, identifier, text='AAA')
        path = Path(self.target.source(identifier)['path'])
        previous = path.stat()
        path.write_bytes(b'BBB')
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        self.transfer.export_backup(self.source, self.archive)
        with self.assertRaisesRegex(ValueError, '冲突'):
            self.transfer.restore_backup(self.target, self.archive)
        self.assertEqual(path.read_bytes(), b'BBB')

    def test_invalid_record_path_and_duplicate_chunk_are_rejected(self):
        self.document(self.source)
        for modification in ['path', 'ordinal']:
            if self.archive.exists():
                self.archive.unlink()
            self.transfer.export_backup(self.source, self.archive)
            def mutate(rows):
                result = []
                for item, data in rows:
                    if item.filename == 'manifest.json':
                        manifest = json.loads(data)
                        record = manifest['documents'][0]
                        if modification == 'path':
                            record['document']['path'] = '../escape.txt'
                        else:
                            record['chunks'][1]['ordinal'] = record['chunks'][0]['ordinal']
                        data = json.dumps(manifest).encode()
                    result.append((item, data))
                return result
            self.rewrite(mutate)
            with self.assertRaises(ValueError):
                self.transfer.restore_backup(self.target, self.archive)
            self.assert_empty_target()

    def test_oversized_chunk_rejected_on_export_and_restore(self):
        identifier = self.document(self.source)
        self.transfer.export_backup(self.source, self.archive)
        def oversized(rows):
            result = []
            for item, data in rows:
                if item.filename == 'manifest.json':
                    manifest = json.loads(data)
                    manifest['documents'][0]['chunks'][0]['text'] = '字' * 16001
                    data = json.dumps(manifest, ensure_ascii=False).encode()
                result.append((item, data))
            return result
        self.rewrite(oversized)
        with self.assertRaises(ValueError):
            self.transfer.restore_backup(self.target, self.archive)
        self.assert_empty_target()
        self.archive.unlink()
        with self.source.store.db() as db:
            path = db.execute('SELECT path FROM kb_documents WHERE id=?', (identifier,)).fetchone()[0]
            db.execute('UPDATE chunks SET text=? WHERE path=? AND ordinal=3', ('字' * 16001, path))
        with self.assertRaises(ValueError):
            self.transfer.export_backup(self.source, self.archive)
        self.assertFalse(self.archive.exists())

    def test_database_failure_rolls_back_records_and_only_new_directories(self):
        existing = self.document(self.target, title='已有资料')
        self.document(self.source)
        self.document(self.source, title='触发失败')
        self.transfer.export_backup(self.source, self.archive)
        with self.target.store.db() as db:
            db.execute("CREATE TRIGGER reject_import BEFORE INSERT ON kb_documents WHEN new.title='触发失败' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with self.assertRaises((ValueError, sqlite3.DatabaseError)):
            self.transfer.restore_backup(self.target, self.archive)
        self.assertEqual(self.target.list()['total'], 1)
        self.assertEqual([p.name for p in (self.target.store.root / 'documents').iterdir()], [existing])
        self.assertEqual(self.target.read(existing)['chunks'][0]['text'], '原始内容')

    def test_export_does_not_overwrite_or_accept_changed_original(self):
        identifier = self.document(self.source)
        self.archive.write_bytes(b'existing backup')
        with self.assertRaises((ValueError, FileExistsError)):
            self.transfer.export_backup(self.source, self.archive)
        self.assertEqual(self.archive.read_bytes(), b'existing backup')
        self.archive.unlink()
        Path(self.source.source(identifier)['path']).write_text('原件已修改', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.transfer.export_backup(self.source, self.archive)
        self.assertFalse(self.archive.exists())


if __name__ == '__main__':
    unittest.main()
