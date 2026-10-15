"""Index text and source-coordinate text must share one Unicode contract."""
import random

from cn_contract.library.text import normalize, tokens


def test_compatibility_expansion_whitespace_and_original_positions():
    source = ' Ａßﬁe\u0301\n\t甲\u200b乙  '
    normalized, positions = normalize(source, with_map=True)
    assert normalized == ' assfie\u0301 甲乙 '
    assert normalize(source) == normalized
    start = normalized.index('甲乙')
    assert source[positions[start]:positions[start+1]+1] == '甲\u200b乙'
    assert positions[2] == positions[3] == source.index('ß')


def test_token_namespaces_and_v1_unassigned_character_boundaries():
    assert tokens('租赁合同 abc12。甲𠀀_') == ['h租赁','h赁合','h合同','b','w6162633132','b','h甲𠀀','b']
    assert tokens('\U0002f68c') == ['s\U0002f68c']
    # Preserve v1: non-alphanumeric runs after punctuation are separators.
    assert tokens('。\U0002f68c') == ['b']


def test_index_normalization_equals_mapped_normalization_for_unicode():
    randomizer = random.Random(917)
    for _ in range(500):
        source = ''.join(chr(randomizer.randrange(0x110000)) for _ in range(40))
        mapped, positions = normalize(source, with_map=True)
        assert normalize(source) == mapped
        assert len(mapped) == len(positions)
        assert positions == sorted(positions)
        assert all(0 <= p < len(source) for p in positions)
