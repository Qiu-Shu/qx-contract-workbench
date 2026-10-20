"""Single-span mapping preserves the existing Unicode contract without full maps."""
import random
import tracemalloc

import pytest

from cn_contract.library.text import normalize, original_span


@pytest.mark.parametrize('source', ['㍻年 Ａßﬁ', 'e\u0301\r\n\t甲\u200b乙  ',
    '  \ufeff\u200c\u200d\u2060\t  \r\n甲', '𠀀😀abc', '甲\u200b\t\t乙', '甲\u200b', 'ﬃ'])
def test_every_nonempty_span_matches_original_coordinate_contract(source):
    normalized, positions = normalize(source, with_map=True)
    for start in range(len(normalized)):
        for end in range(start + 1, len(normalized) + 1):
            assert original_span(source, start, end) == (positions[start], positions[end - 1] + 1)


def test_random_unicode_spans_preserve_mapping():
    rng = random.Random(3617)
    for _ in range(200):
        source = ''.join(chr(rng.randrange(0x110000)) for _ in range(40))
        normalized, positions = normalize(source, with_map=True)
        for _ in range(10):
            start = rng.randrange(len(normalized))
            end = rng.randrange(start + 1, len(normalized) + 1)
            assert original_span(source, start, end) == (positions[start], positions[end - 1] + 1)


@pytest.mark.parametrize('start,end', [(-1,1),(0,0),(2,1),(0,4),(True,2),(0,False),(0.0,1),(0,'1')])
def test_invalid_normalized_spans_have_one_fixed_error(start, end):
    with pytest.raises(ValueError, match='^NORMALIZED_RANGE_INVALID$'):
        original_span('甲乙丙', start, end)


def test_empty_or_invisible_only_source_cannot_supply_a_span():
    for source in ('', '\u200b\u2060'):
        with pytest.raises(ValueError, match='^NORMALIZED_RANGE_INVALID$'):
            original_span(source, 0, 1)


def test_long_text_span_does_not_allocate_a_full_character_map():
    source = '甲乙丙丁。' * 40000 + '㍻年'
    normalize('甲乙丙丁。㍻年')  # Warm the same fixed alphabet before measuring.
    tracemalloc.start()
    try:
        result = original_span(source, 200001, 200003)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result == (200000, 200002)
    assert peak < 1024 * 1024
