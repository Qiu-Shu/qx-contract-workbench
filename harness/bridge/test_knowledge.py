import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from knowledge import KnowledgeStore


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.kb = KnowledgeStore(self.directory.name)

    def document(self, chunks):
        identifier = str(uuid4())
        path = self.kb.store.root / 'documents' / identifier / '范本.txt'
        path.parent.mkdir(parents=True)
        path.write_text(''.join(chunks), encoding='utf-8')
        self.kb.register(identifier, path.name)
        key = self.kb.store.key(path)
        with self.kb.store.db() as db:
            for ordinal, value in enumerate(chunks):
                db.execute('INSERT INTO chunks VALUES(?,?,?,?,?)', (key, ordinal, None, f'text:{ordinal}', value))
        self.kb.set_state(identifier, 'ready')
        return identifier, path

    def test_boundary_match_has_both_verifiable_citations(self):
        identifier, _ = self.document(['x' * 3998 + '劳动', '合同解除'])
        matches = self.kb.search('劳动合同')['matches']
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertIn('劳动合同', match['excerpt'])
        self.assertEqual(len(match['citations']), 2)
        self.assertEqual(''.join(self.kb.citation(c['citation'])['text'] for c in match['citations'])[-6:], '劳动合同解除')
        self.kb.archive(identifier)
        self.assertEqual(self.kb.search('劳动合同')['matches'], [])

    def test_short_and_fulltext_search_pagination(self):
        for _ in range(3):
            self.document(['劳动合同'])
        for term in ['劳动', '劳动合同']:
            first = self.kb.search(term, limit=2)
            second = self.kb.search(term, offset=2, limit=2)
            self.assertTrue(first['has_more'])
            self.assertEqual(len(second['matches']), 1)
            self.assertNotIn(second['matches'][0]['document_id'], [m['document_id'] for m in first['matches']])

    def test_existing_chunks_are_backfilled_when_fts_is_created(self):
        self.document(['劳动合同'])
        with self.kb.store.db() as db:
            for name in ['insert', 'delete', 'update']:
                db.execute(f'DROP TRIGGER kb_chunks_{name}')
            db.execute('DROP TABLE kb_fts')
        reopened = KnowledgeStore(self.directory.name)
        self.assertEqual(len(reopened.search('劳动合同')['matches']), 1)

    def test_changed_source_cannot_be_quoted(self):
        _, path = self.document(['劳动合同'])
        ref = self.kb.search('劳动合同')['matches'][0]['citation']
        path.write_text('changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.kb.citation(ref)

    def test_reparsed_chunk_cannot_silently_change_an_existing_reference(self):
        self.document(['劳动合同'])
        ref = self.kb.search('劳动合同')['matches'][0]['citation']
        with self.kb.store.db() as db:
            db.execute("UPDATE chunks SET text='不同解析内容'")
        with self.assertRaisesRegex(ValueError, '解析'):
            self.kb.citation(ref)

    def test_upgrade_repairs_preexisting_incomplete_fulltext_index(self):
        self.document(['劳动合同'])
        with self.kb.store.db() as db:
            db.execute('DELETE FROM kb_fts')
            db.execute('DROP TABLE IF EXISTS kb_migrations')
        self.assertEqual(len(KnowledgeStore(self.directory.name).search('劳动合同')['matches']), 1)


if __name__ == '__main__':
    unittest.main()
