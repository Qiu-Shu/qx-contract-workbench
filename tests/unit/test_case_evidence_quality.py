"""Versioned rendering on synthetic evidence; no claim of semantic verification."""
from types import SimpleNamespace

import pytest

from cn_contract import domain as d
from cn_contract.assistant import case_evidence
from cn_contract.assistant.providers.policy import sha


LEGACY_SYSTEM_SHA = 'bbfa80940b06bc18a9cef4414094017bf16823564f51bdb8b359faa2c1618156'
SOURCE_IDS = ('a' * 64, 'b' * 64)
ORIGINALS = ('甲称尾款尚未付清。', '乙要求先核对破损和已付款项。')


def evidence(*, legacy=False):
    snapshot = (d.CaseMethodSnapshot(method_id='case-evidence-v1', method_sha256=LEGACY_SYSTEM_SHA)
        if legacy else case_evidence.select_method('case', '起草文书并整理时间线', method_id='case-evidence-v2'))
    manifest = SimpleNamespace(case_method=snapshot, knowledge=None, sources=tuple(
        SimpleNamespace(source_id=source_id, reference=SimpleNamespace(kind='message', quote=text))
        for source_id, text in zip(SOURCE_IDS, ORIGINALS)))
    data = dict(format_version='case-evidence-v1', quotes=[dict(id=f'q{i}', source_id=source_id,
        start=0, end=len(text), exact_quote=text) for i, (source_id, text) in enumerate(zip(SOURCE_IDS, ORIGINALS))],
        statements=[
            dict(kind='proposed_text', text='甲主张尾款未付，数额为【待补】。',
                support=['q0'], opposing=[], unresolved=['待核对款项凭证']),
            dict(kind='source_statement', text='乙要求先核账，不等于否认欠款。',
                support=['q1'], opposing=[], unresolved=['待核对双方账户']),
            dict(kind='proposed_text', text='乙要求核对破损及已付款项，结算结果待核。',
                support=['q1'], opposing=[], unresolved=['待补破损记录'])],
        timeline=[], gaps=['双方未提交完整结算单'])
    return manifest, data


def test_explicit_v2_selection_keeps_original_result_schema():
    manifest, data = evidence()
    assert manifest.case_method.method_id == 'case-evidence-v2'
    assert case_evidence.candidate(data, manifest).case_evidence.format_version == 'case-evidence-v1'


def test_frozen_v1_system_and_explicit_historical_selection_are_unchanged():
    assert case_evidence.METHOD_ID == 'case-evidence-v1'
    assert sha(case_evidence.SYSTEM) == LEGACY_SYSTEM_SHA
    selected = case_evidence.select_method('case', '请写文书', method_id='case-evidence-v1')
    assert selected == d.CaseMethodSnapshot(method_id='case-evidence-v1', method_sha256=LEGACY_SYSTEM_SHA)
    assert case_evidence.method_system(selected) == case_evidence.SYSTEM


def test_frozen_v1_rendering_is_exact_even_with_interleaved_proposed_paragraphs():
    manifest, data = evidence(legacy=True)
    expected = '\n'.join([
        '案件整理候选｜待律师核实', '引文位置已校验；不代表事实成立、推断正确或法律依据已核验。',
        '\n拟写文书（未签发）：甲主张尾款未付，数额为【待补】。', f'依据：q0 [{SOURCE_IDS[0]}]', '待核：待核对款项凭证',
        '\n材料陈述（未认定）：乙要求先核账，不等于否认欠款。', f'依据：q1 [{SOURCE_IDS[1]}]', '待核：待核对双方账户',
        '\n拟写文书（未签发）：乙要求核对破损及已付款项，结算结果待核。', f'依据：q1 [{SOURCE_IDS[1]}]', '待核：待补破损记录',
        '\n逐字引文（位置相对该来源原文，起始含、结束不含）',
        f'q0 [{SOURCE_IDS[0]}] 字符 0–{len(ORIGINALS[0])}：{ORIGINALS[0]}',
        f'q1 [{SOURCE_IDS[1]}] 字符 0–{len(ORIGINALS[1])}：{ORIGINALS[1]}',
        '\n证据缺口与未核事项', '待核：双方未提交完整结算单'])
    assert case_evidence.candidate(data, manifest).text == expected


def test_proposed_paragraphs_are_contiguous_with_references_and_checks_after_body():
    manifest, data = evidence()
    output = case_evidence.candidate(data, manifest)
    body, review = output.text.split('\n文书段落复核（依据与待核事项）', 1)
    assert '\n\n'.join((data['statements'][0]['text'], data['statements'][2]['text'])) in body
    assert '依据：' not in body and '待核：' not in body
    assert '第1段' in review and '第2段' in review
    assert f'依据：q0 [{SOURCE_IDS[0]}]' in review and f'依据：q1 [{SOURCE_IDS[1]}]' in review
    assert '待核对款项凭证' in review and '待补破损记录' in review
    assert '材料陈述（未认定）：' in review
    assert output.case_evidence == d.CaseEvidenceDraft.model_validate(data)
    assert output.citations == SOURCE_IDS


def test_compatible_statements_are_not_promoted_to_confirmed_opposition_by_display():
    manifest, data = evidence()
    data['statements'][0]['opposing'] = ['q1']
    data['timeline'] = [dict(id=f'e{i}', event_text=text, raw_date='', quote_ids=[f'q{i}'],
        conflict_group='settlement', uncertainty='两种说法可能同时成立，需核对关系')
        for i, text in enumerate(ORIGINALS)]
    output = case_evidence.candidate(data, manifest)
    assert '相反来源（模型标注，关系待核）' in output.text
    assert '待核冲突组 settlement（模型标注，尚未认定矛盾）' in output.text
    assert '相反来源：' not in output.text
    # The host retains the model relation for review; it cannot decide entailment.
    assert output.case_evidence.statements[0].opposing == ('q1',)
    assert all(event.conflict_group == 'settlement' for event in output.case_evidence.timeline)


def test_no_document_section_is_invented_for_chronology_only():
    manifest, data = evidence()
    data['statements'] = []
    data['timeline'] = [dict(id=f'e{i}', event_text=text, raw_date='', quote_ids=[f'q{i}'],
        conflict_group=None, uncertainty='原件待核') for i, text in enumerate(ORIGINALS)]
    output = case_evidence.candidate(data, manifest)
    assert '拟写文书' not in output.text and '文书段落复核' not in output.text
    assert '时间线 e0' in output.text and '时间线 e1' in output.text


@pytest.mark.parametrize('legacy', [False, True])
def test_quote_tampering_still_fails_for_both_versions(legacy):
    manifest, data = evidence(legacy=legacy)
    data['quotes'][0]['exact_quote'] = '甲称尾款已经付清。'
    with pytest.raises(ValueError, match='CASE_EVIDENCE_QUOTE_INVALID'):
        case_evidence.candidate(data, manifest)


@pytest.mark.parametrize('method_id', ['case-evidence-v1', 'case-evidence-v2'])
def test_method_version_and_digest_are_bound(method_id):
    selected = case_evidence.select_method('case', '整理时间线', method_id=method_id)
    assert sha(case_evidence.method_system(selected)) == selected.method_sha256
    with pytest.raises(ValueError, match='CASE_METHOD_INVALID'):
        case_evidence.method_system(selected.model_copy(update={'method_sha256': 'f' * 64}))


def test_unknown_version_is_not_silently_routed_to_current():
    with pytest.raises(ValueError, match='CASE_METHOD_INVALID'):
        case_evidence.select_method('case', '整理时间线', method_id='case-evidence-v999')
