"""Opt-in actual bundled OCR, distinct from controlled parser-boundary checks."""
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

import reader
from store import MaterialStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from document_complexity_fixture import continued_pdf, mixed_pdf, inline_mixed_pdf, table_image, TITLE, HEADERS, FIRST, SECOND, OTHER

pytestmark = pytest.mark.skipif(os.name != 'nt' or os.environ.get('QX_COMPLEX_OCR') != '1',
                              reason='actual bundled Windows OCR requires explicit QX_COMPLEX_OCR=1')


def chunks(store, path, page=None):
    result = []; start = 0
    while True:
        response = store.read(path, start=start, limit=12, page=page)
        result.extend(response['chunks'])
        if response['next_start'] is None: return result
        start = response['next_start']


def layout(chunk):
    return json.loads(chunk['location'].split(':layout:', 1)[1].rsplit(':chars:', 1)[0])


def unchanged(path):
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def test_actual_scanned_continuation_keeps_cells_pages_and_incremental_identity(tmp_path):
    source = tmp_path / 'synthetic-continued.pdf'; continued_pdf(source)
    before = unchanged(source); store = MaterialStore(tmp_path); store.register(source)
    first = reader.parse(store, source, start_page=1, page_count=1)
    assert (first['status'], first['next_page']) == ('partial', 2)
    reader.parse(store, source, start_page=3, page_count=1)
    last = reader.parse(store, source, start_page=2, page_count=1)
    assert last['status'] == 'ready' and last['failed_pages'] == []
    all_rows = chunks(store, source)
    for number, expected in ((1, FIRST), (2, SECOND), (3, OTHER)):
        actual = [c for c in all_rows if c['page'] == number]
        for values in expected:
            row = next(c for c in actual if c['text'] == '\t'.join(values))
            info = layout(row)
            assert len(info['scan_grid']['cells']) == 3
            if number == 2:
                assert info['header_continuation']['from_page'] == 1
                assert [b['headers'][-1]['value'] for b in info['header_bindings']] == HEADERS
            if number == 3:
                assert 'header_continuation' not in info
                assert not info.get('header_bindings')
    reader.parse(store, source, start_page=1, page_count=1)
    assert chunks(store, source) == all_rows
    assert unchanged(source) == before


def test_actual_mixed_native_and_scan_page_preserves_both_layers_once(tmp_path):
    source = tmp_path / 'synthetic-mixed.pdf'; mixed_pdf(source)
    before = unchanged(source); store = MaterialStore(tmp_path); store.register(source)
    assert reader.parse(store, source)['status'] == 'ready'
    actual = chunks(store, source)
    text = '\n'.join(c['text'] for c in actual)
    assert text.count('SYNTHETIC-NATIVE-2026') == 1
    assert '\t'.join(FIRST[0]) in text
    assert all(c['page'] == 1 for c in actual)
    assert any(':native:' in c['location'] for c in actual)
    assert any(':ocr-row:' in c['location'] for c in actual)
    assert unchanged(source) == before


def test_actual_rotated_scan_preserves_text_and_declares_coordinate_space(tmp_path):
    source = tmp_path / 'synthetic-rotated.png'
    image = table_image(TITLE, [HEADERS, FIRST[0]])
    rotated = image.rotate(90, expand=True)
    try: rotated.save(source)
    finally: rotated.close(); image.close()
    before = unchanged(source); store = MaterialStore(tmp_path); store.register(source)
    assert reader.parse(store, source)['status'] == 'ready'
    actual = chunks(store, source)
    assert any(c['text'] == '\t'.join(FIRST[0]) for c in actual)
    for chunk in actual:
        info = layout(chunk)
        assert info['rotation_degrees'] in (90, 270)
        width, height = info['image_size']
        for box in info['boxes']:
            assert all(0 <= x <= width and 0 <= y <= height for x, y in box)
    assert unchanged(source) == before


def test_actual_native_and_scan_on_the_same_line_are_not_duplicated(tmp_path):
    source = tmp_path / 'synthetic-inline.pdf'; inline_mixed_pdf(source)
    before = unchanged(source); store = MaterialStore(tmp_path); store.register(source)
    assert reader.parse(store, source)['status'] == 'ready'
    text = '\n'.join(c['text'] for c in chunks(store, source))
    assert text.count('SYNTHETIC-NATIVE-2026') == 1
    # Bundled OCR can omit the printed word space (retained as a known error in
    # delivery evidence). This assertion checks content/duplication, not spacing fidelity.
    assert ''.join(text.split()).count('SCANNEDBODY') == 1
    assert unchanged(source) == before
