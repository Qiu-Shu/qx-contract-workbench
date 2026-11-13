"""Real PDF/import with controlled recognition: deduplication is position-specific."""
import hashlib
from pathlib import Path
import sys

import pytest
import reader
from store import MaterialStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from document_complexity_fixture import native_pdf


@pytest.mark.parametrize('repeat_elsewhere', [False, True])
def test_mixed_ocr_row_deduplicates_native_only_at_the_same_position(tmp_path, monkeypatch, repeat_elsewhere):
    from cn_contract.documents import material_ocr
    import material_scan
    source = tmp_path / 'fictional.pdf'; source.write_bytes(native_pdf())
    before = hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns
    def block(x, y, width, text):
        return ([[x, y], [x + width, y], [x + width, y + 32], [x, y + 32]], text, .99)
    blocks = [block(60, 40, 450, 'SYNTHETIC-NATIVE-2026'), block(700, 40, 400, 'SCANNED BODY')]
    if repeat_elsewhere: blocks.append(block(60, 250, 450, 'SYNTHETIC-NATIVE-2026'))
    monkeypatch.setattr(material_ocr, 'recognize', lambda _: blocks)
    def no_model(*args, **kwargs): raise AssertionError('Controlled recognition test must not run a model')
    monkeypatch.setattr(material_scan, '_local_recognize', no_model)
    store = MaterialStore(tmp_path); store.register(source)
    assert reader.parse(store, source, force_ocr=True)['status'] == 'ready'
    chunks = store.read(source, limit=12)['chunks']; text = '\n'.join(c['text'] for c in chunks)
    assert text.count('SYNTHETIC-NATIVE-2026') == (2 if repeat_elsewhere else 1)
    assert text.count('SCANNED BODY') == 1
    # Count alone could hide one duplicate and one incorrectly removed occurrence.
    assert [c['text'] for c in chunks if ':ocr-row:' in c['location']] == (
        ['SCANNED BODY', 'SYNTHETIC-NATIVE-2026'] if repeat_elsewhere else ['SCANNED BODY'])
    assert all(c['page'] == 1 for c in chunks)
    assert before == (hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns)
