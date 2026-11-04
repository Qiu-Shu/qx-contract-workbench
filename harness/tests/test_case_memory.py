"""Synthetic cases only; no external service or real legal material is used."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from case_memory import CaseMemoryStore, HindsightAdapter


class FakeAdapter:
    key = 'synthetic-index'

    def __init__(self):
        self.banks = {}
        self.calls = []
        self.failure = False
        self.delete_failure = False
        self.on_retain = None
        self.on_recall = None
        self.hits = None
        self.ready_failure = False

    def ready(self):
        if self.ready_failure:
            raise RuntimeError('Synthetic engine not ready')

    def retain(self, bank, rows):
        self.calls.append(('retain', bank))
        self.banks.setdefault(bank, []).extend(dict(row) for row in rows)
        if self.on_retain:
            self.on_retain()
        if self.failure:
            raise RuntimeError('Synthetic service unavailable, secret must not escape')

    def recall(self, bank, query):
        self.calls.append(('recall', bank))
        if self.on_recall:
            self.on_recall()
        if self.failure:
            raise RuntimeError('Synthetic failure')
        if self.hits is not None:
            return self.hits
        return [{'document_id': row['id']+'-r'+str(row['revision']), 'text': 'never return generated text'}
                for row in self.banks.get(bank, [])]

    def delete_bank(self, bank):
        self.calls.append(('delete', bank))
        if self.delete_failure:
            raise RuntimeError('Synthetic delete failure')
        self.banks.pop(bank, None)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'QX_HINDSIGHT_URL': ''})
        self.env.start()
        self.adapter = FakeAdapter()
        self.store = CaseMemoryStore(self.temp.name, self.adapter)
        self.a = self.store.cases.create('Synthetic case A')['id']
        self.b = self.store.cases.create('Synthetic case B')['id']

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def add(self, content='Synthetic lease claim'):
        return self.store.add(self.a, content=content, source='Synthetic interview', confirmed=True)['memory']

    def test_default_enabled_and_no_automatic_ingest(self):
        self.store.cases.add_note(self.a, 'interview', 'Unselected private notes')
        self.assertTrue(self.store.status(self.a)['enabled'])
        self.assertEqual(self.store.list(self.a)['total'], 0)
        self.assertEqual(self.store.recall(self.a, 'private')['matches'], [])
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.store.status()['sync_state'], 'pending')
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'empty')
        self.assertEqual(self.adapter.calls, [])
        with self.store.cases.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM case_memory_banks').fetchone()[0], 0)
        self.assertFalse(CaseMemoryStore(self.temp.name).status(self.a)['service_configured'])

    def test_note_provenance_and_crosscase_spoof(self):
        note = self.store.cases.add_note(self.a, 'interview', 'Synthetic client quote', source='Interview sheet')
        for kwargs in ({'case_id': self.b, 'note_id': note['id']},
                       {'case_id': self.a, 'note_id': note['id'], 'content': 'spoof'},
                       {'case_id': self.a, 'note_id': note['id'], 'source': 'spoof'}):
            with self.assertRaises(ValueError):
                self.store.add(**kwargs)
        memory = self.store.add(self.a, note_id=note['id'])['memory']
        self.assertEqual(memory['content'], note['content'])
        self.assertEqual(memory['source']['snapshot'], note['content'])
        self.assertEqual(memory['source']['note_id'], note['id'])
        for action in (lambda: self.store.read(self.b, memory['id']),
                       lambda: self.store.update(self.b, memory['id'], 1, 'spoof'),
                       lambda: self.store.delete(self.b, memory['id'], 1),
                       lambda: self.store.sync('unknown-case')):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(self.store.recall(self.b, 'Synthetic')['matches'], [])

    def test_manual_requires_confirmation_and_source(self):
        for kwargs in ({'source': 'x'}, {'confirmed': True}, {'source': '', 'confirmed': True}):
            with self.assertRaises(ValueError):
                self.store.add(self.a, content='Synthetic', **kwargs)
        memory = self.add()
        self.assertEqual(self.store.read(self.a, memory['id'])['revision'], 1)

    def test_recall_returns_only_current_local_sources(self):
        memory = self.add()
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'ready')
        result = self.store.recall(self.a, 'unrelated semantic term', use_hindsight=True)
        self.assertEqual(result['mode'], 'hindsight')
        self.assertEqual(result['matches'][0]['content'], memory['content'])
        self.assertEqual(result['matches'][0]['source'], memory['source'])
        self.adapter.hits = [{'document_id': 'unknown', 'text': 'Other case private data'}]
        self.assertEqual(self.store.recall(self.a, 'unknown', use_hindsight=True)['matches'], [])

    def test_edit_revision_invalidates_semantics_and_preserves_snapshot(self):
        memory = self.add('obsolete content')
        self.store.sync(self.a)
        corrected = self.store.update(self.a, memory['id'], 1, 'corrected content')['memory']
        self.assertEqual(corrected['revision'], 2)
        self.assertEqual(corrected['source']['snapshot'], 'obsolete content')
        self.assertEqual(self.store.recall(self.a, 'obsolete', use_hindsight=True)['matches'], [])
        self.assertEqual(self.store.recall(self.a, 'corrected', use_hindsight=True)['mode'], 'local_fallback')
        with self.assertRaises(ValueError):
            self.store.delete(self.a, memory['id'], 1)
        self.assertEqual(self.store.sync(self.a)['pending_cleanup'], 0)

    def test_delete_physically_purges_snapshot_and_durable_cleanup(self):
        marker = 'SYNTHETIC_MEMORY_MUST_BE_PURGED_891224'
        memory = self.add(marker)
        self.store.sync(self.a)
        self.adapter.delete_failure = True
        deleted = self.store.delete(self.a, memory['id'], 1)
        self.assertTrue(deleted['deleted'])
        self.assertEqual(deleted['pending_cleanup'], 1)
        with self.store.cases.db() as db:
            self.assertIsNone(db.execute('SELECT * FROM case_memories WHERE id=?', (memory['id'],)).fetchone())
        self.assertNotIn(marker.encode(), self.store.cases.db_path.read_bytes())
        resumed = CaseMemoryStore(self.temp.name, self.adapter)
        resumed.sync(self.a)
        self.assertGreater(resumed.status(self.a)['pending_cleanup'], 0)
        self.adapter.delete_failure = False
        self.assertEqual(resumed.sync(self.a)['pending_cleanup'], 0)
        self.assertEqual(resumed.recall(self.a, marker, use_hindsight=True)['matches'], [])

    def test_disabled_allows_management_and_cleanup_only(self):
        memory = self.add()
        self.store.sync(self.a)
        self.store.settings(False, self.a)
        self.adapter.calls.clear()
        self.assertEqual(self.store.recall(self.a, 'Synthetic', use_hindsight=True)['mode'], 'disabled')
        self.assertEqual(self.store.list(self.a)['total'], 1)
        self.assertEqual(self.store.read(self.a, memory['id'])['id'], memory['id'])
        with self.assertRaises(ValueError):
            self.add()
        self.store.sync(self.a)
        self.assertTrue(all(call[0] == 'delete' for call in self.adapter.calls))
        self.store.settings(True, self.a)
        self.store.settings(False)
        self.assertFalse(self.store.status(self.b)['enabled'])

    def test_service_failure_keeps_local_write_and_uncertain_cleanup(self):
        memory = self.add()
        self.adapter.failure = True
        status = self.store.sync(self.a)
        self.assertEqual(status['sync_state'], 'error')
        self.assertGreater(status['pending_cleanup'], 0)
        self.assertNotIn('secret', status['last_error'])
        self.assertEqual(self.store.read(self.a, memory['id'])['content'], memory['content'])
        self.assertEqual(self.store.recall(self.a, 'Synthetic', use_hindsight=True)['mode'], 'local_fallback')
        self.adapter.failure = False
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'ready')
        self.assertGreater(self.store.status(self.a)['pending_cleanup'], 0)

    def test_edit_during_retain_cannot_activate_stale_generation(self):
        memory = self.add('original')
        self.adapter.on_retain = lambda: self.store.update(self.a, memory['id'], 1, 'changed')
        status = self.store.sync(self.a)
        self.assertEqual(status['sync_state'], 'pending')
        self.assertEqual(self.store.recall(self.a, 'original', use_hindsight=True)['matches'], [])
        self.adapter.on_retain = None
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'ready')

    def test_delete_during_recall_cannot_return_deleted_result(self):
        memory = self.add()
        self.store.sync(self.a)
        self.adapter.on_recall = lambda: self.store.delete(self.a, memory['id'], 1)
        self.assertEqual(self.store.recall(self.a, 'Synthetic', use_hindsight=True)['matches'], [])

    def test_source_correction_is_visible_and_excluded(self):
        note = self.store.cases.add_note(self.a, 'interview', 'old assertion', source='Synthetic sheet')
        memory = self.store.add(self.a, note_id=note['id'])['memory']
        self.store.sync(self.a)
        correction = self.store.cases.add_note(self.a, 'interview', 'corrected assertion', supersedes=note['id'])
        self.assertEqual(self.store.recall(self.a, 'assertion', use_hindsight=True)['matches'], [])
        current = self.store.read(self.a, memory['id'])
        self.assertTrue(current['source_changed'])
        self.assertEqual(current['current_source_note_ids'], [correction['id']])
        self.assertEqual(self.store.list(self.a)['memories'][0]['current_source_note_ids'], [correction['id']])
        self.assertEqual(current['source']['snapshot'], 'old assertion')
        self.assertEqual([n['id'] for n in self.store.sources(self.a)['notes']], [correction['id']])

    def test_pagination_and_case_namespaces(self):
        for i in range(3):
            self.add('item '+str(i))
        page = self.store.list(self.a, limit=2)
        self.assertEqual(page['next_offset'], 2)
        self.assertEqual(len(self.store.list(self.a, offset=2, limit=2)['memories']), 1)
        self.store.sync(self.a)
        self.store.add(self.b, content='second case', source='synthetic', confirmed=True)
        self.store.sync(self.b)
        self.assertEqual(len(self.adapter.banks), 2)
        self.assertTrue(all(len({r['case_id'] for r in rows}) == 1 for rows in self.adapter.banks.values()))

    def test_abandoned_staging_is_durably_reaped(self):
        with self.store.cases.db() as db:
            self.store._state(db, self.a)
            db.execute('INSERT INTO case_memory_banks VALUES(?,?,?,?,?,?,0)',
                       ('qx-abcd', self.a, 0, self.adapter.key, 'building', time.time()-1))
        self.store.sync(self.a)
        self.assertIn(('delete', 'qx-abcd'), self.adapter.calls)
        self.assertGreater(self.store.status(self.a)['pending_cleanup'], 0)

    def test_large_generation_resumes_bounded_batches(self):
        for i in range(12):
            self.add('Synthetic '+str(i))
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'pending')
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'pending')
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'ready')
        self.assertEqual(len(self.adapter.banks), 1)
        self.assertEqual(len(next(iter(self.adapter.banks.values()))), 12)
        self.assertEqual(len([c for c in self.adapter.calls if c[0] == 'retain']), 3)

    def test_unready_service_never_creates_uncertain_banks(self):
        self.add()
        self.adapter.ready_failure = True
        for _ in range(3):
            self.assertEqual(self.store.sync(self.a)['sync_state'], 'error')
        with self.store.cases.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM case_memory_banks').fetchone()[0], 0)

    def test_failed_semantic_recall_schedules_rebuild_from_current_local_rows(self):
        self.add('Synthetic recoverable memory')
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'ready')
        old_bank = next(iter(self.adapter.banks))
        self.adapter.failure = True
        fallback = self.store.recall(self.a, 'recoverable')
        self.assertEqual(fallback['mode'], 'local_fallback')
        self.assertEqual(fallback['sync_state'], 'error')
        self.assertTrue(fallback['matches'])
        self.adapter.failure = False
        self.assertEqual(self.store.sync(self.a)['sync_state'], 'ready')
        self.store.sync(self.a)
        self.assertNotIn(old_bank, self.adapter.banks)


class AdapterTests(unittest.TestCase):
    def test_loopback_only_and_stable_instance(self):
        for url in ('https://example.com:443', 'http://localhost:8888', 'http://127.0.0.1:80/path',
                    'http://user:pass@127.0.0.1:80', 'http://127.0.0.1:80?secret=x'):
            with self.assertRaises(ValueError):
                HindsightAdapter(url)
        self.assertEqual(HindsightAdapter('http://127.0.0.1:1234', instance_id='persistent').key,
                         HindsightAdapter('http://127.0.0.1:1235', instance_id='persistent').key)

    def test_http_contract_and_redirect_block(self):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path, body, self.headers.get('Authorization')))
                if body.get('query') == 'redirect':
                    self.send_response(302);self.send_header('Location', 'http://example.com');self.end_headers();return
                value = {'results': []} if self.path.endswith('/recall') else {
                    'success': True, 'async': False, 'bank_id': 'qx-abcd', 'items_count': len(body['items'])}
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())

            def do_DELETE(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'{"success":true}')

            def do_GET(self):
                calls.append((self.path, None, self.headers.get('Authorization')))
                self.send_response(200);self.end_headers();self.wfile.write(b'{"status":"ready"}')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            adapter = HindsightAdapter('http://127.0.0.1:'+str(server.server_port), 'synthetic-token')
            adapter.retain('qx-abcd', [{'id': 'm', 'revision': 2, 'case_id': 'a', 'source_sha256': 'hash', 'content': 'synthetic'}])
            adapter.recall('qx-abcd', 'synthetic')
            adapter.delete_bank('qx-abcd')
            self.assertFalse(calls[0][1]['async'])
            self.assertEqual(calls[0][1]['items'][0]['document_id'], 'm-r2')
            self.assertEqual(calls[0][2], 'Bearer synthetic-token')
            self.assertEqual(calls[1][1]['types'], ['world', 'experience'])
            adapter.ready()
            self.assertEqual(calls[-1][0], '/health/ready')
            managed = HindsightAdapter('http://127.0.0.1:'+str(server.server_port)+'/engine', 'synthetic-token')
            managed.ready()
            self.assertEqual(calls[-1][0], '/engine/health/ready')
            managed.recall('qx-abcd', 'synthetic')
            self.assertEqual(calls[-1][0], '/engine/v1/default/banks/qx-abcd/memories/recall')
            with self.assertRaises(ValueError):
                adapter.recall('qx-abcd', 'redirect')
        finally:
            server.shutdown();server.server_close();worker.join()


if __name__ == '__main__':
    unittest.main()
