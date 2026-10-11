"""Versioned synthetic evaluation, separate from historical field hit counts."""
import pytest

from cn_contract.acceptance.ocr_scoring import character_errors, score_page


REFERENCE = ['价款28473元', '不得自动验收2026-10-15']


@pytest.mark.parametrize('blocks,expected', [
    (REFERENCE, True),
    (['价款128473元', REFERENCE[1]], False),
    (['价款28473元', '价款284730元', REFERENCE[1]], False),
    (['价款28473元', '价款28473元', REFERENCE[1]], False),
    (['价款28473元', '不得自动验收2', '2026-10-15'], False),
    (['价款−28473元', REFERENCE[1]], False),
    (['价款28473．9元', REFERENCE[1]], False),
    (['价款28473万元', REFERENCE[1]], False),
], ids=['correct', 'wrong_ascii_number', 'conflicting_amount', 'duplicate_amount',
        'cross_box_digit', 'unicode_negative', 'fullwidth_decimal', 'wrong_unit'])
def test_eight_audit_examples_have_strict_expectations(blocks, expected):
    result = score_page(blocks, reference_blocks=REFERENCE, amount='28473', unit='元',
                        date='2026-10-15', prohibition='不得自动验收')
    assert result['version'] == 'synthetic-ocr-v2'
    assert result['fields_match'] is expected
    assert result['full_text']['layout_normalized']['exact'] is expected


def score(blocks, reference=REFERENCE):
    return score_page(blocks, reference_blocks=reference, amount='28473', unit='元',
                      date='2026-10-15', prohibition='不得自动验收')


@pytest.mark.parametrize('reference,recognized,counts', [
    ('甲乙丙', '甲丁丙', (1, 1, 0, 0)),
    ('甲乙丙', '甲丙', (1, 0, 1, 0)),
    ('甲乙丙', '甲丁乙丙', (1, 0, 0, 1)),
    ('甲', '甲乙丙丁', (3, 0, 0, 3)),
    ('甲乙丙', '', (3, 0, 3, 0)),
    ('甲乙丙', '甲乙丙', (0, 0, 0, 0)),
])
def test_full_text_errors_use_known_character_edits(reference, recognized, counts):
    result = character_errors(reference, recognized)
    assert tuple(result[k] for k in ('distance', 'substitutions', 'deletions', 'insertions')) == counts
    assert result['reference_characters'] == len(reference)
    if reference == '甲':
        assert result['cer'] == '3'  # Insertions can exceed the reference length.


def test_fields_full_text_and_layout_are_independent():
    result = score(['价款 28473 元', '不得自动验收 2026-10-15'])
    assert result['fields_match'] is True
    assert result['full_text']['raw']['exact'] is False
    assert result['full_text']['layout_normalized']['exact'] is True
    result = score(['价款２８４７３元', REFERENCE[1]])
    assert result['fields_match'] is True
    assert result['full_text']['layout_normalized']['substitutions'] == 5
    result = score(['错误标题', *REFERENCE], ['虚构标题', *REFERENCE])
    assert result['fields_match'] is True
    assert result['full_text']['layout_normalized']['substitutions'] == 2


def test_amount_details_distinguish_value_sign_and_unit():
    result = score(['价款−28473万元', REFERENCE[1]])['fields']['amount']
    assert result['value_match'] is True
    assert result['sign_match'] is False
    assert result['unit_match'] is False
    assert result['observed'][0]['unit'] == '万元'


@pytest.mark.parametrize('blocks', [
    ['价款2', '8473元', REFERENCE[1]],
    ['价款2 8473元', REFERENCE[1]],
    ['价款28473', '元', REFERENCE[1]],
    ['价款28473', REFERENCE[1]],
    [REFERENCE[0], '不得自动验收2026-10-', '15'],
    [REFERENCE[0], REFERENCE[1], '不得自动验收'],
    [REFERENCE[0], '不得自动验收2026-10-150'],
    [],
])
def test_missing_duplicated_and_fragmented_fields_are_not_reassembled(blocks):
    assert score(blocks)['fields_match'] is False


@pytest.mark.parametrize('reference', [[], [''], ['   '], [REFERENCE[0]],
                                           ['价款999元', REFERENCE[1]]])
def test_invalid_ground_truth_is_rejected(reference):
    with pytest.raises(ValueError):
        score(REFERENCE, reference)


def test_summary_keeps_unscored_pages_and_micro_character_denominators():
    from cn_contract.acceptance.ocr_scoring import summarize_scores
    result = summarize_scores([score(REFERENCE), score([]), None])
    assert result['pages'] == 3
    assert result['scored_pages'] == 2
    assert result['unscored_pages'] == 1
    assert result['field_matches'] == 1
    assert result['full_text']['layout_normalized']['reference_characters'] == 48
    assert result['full_text']['layout_normalized']['distance'] == 24
    assert result['full_text']['layout_normalized']['cer'] == '0.5'
    assert summarize_scores([None])['full_text']['raw']['cer'] is None


@pytest.mark.parametrize('blocks', [
    ['价款− 28473元', REFERENCE[1]],
    ['价款', '−', '28473元', REFERENCE[1]],
    ['价款28473元万元', REFERENCE[1]],
])
def test_detached_signs_and_ambiguous_unit_suffixes_are_not_positive_yuan(blocks):
    assert score(blocks)['fields_match'] is False


def test_amount_detail_is_exact_beyond_decimal_context_precision():
    expected = '1234567890123456789012345678901'
    recognized = '1234567890123456789012345678902'
    result = score_page(['价款' + recognized + '元', REFERENCE[1]],
                        reference_blocks=['价款' + expected + '元', REFERENCE[1]],
                        amount=expected, unit='元', date='2026-10-15', prohibition='不得自动验收')
    assert result['fields']['amount']['value_match'] is False
    assert result['fields']['amount']['match'] is False
