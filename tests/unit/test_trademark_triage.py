"""Trademark triage boundaries with independent fictional material."""
import importlib
import importlib.util

import pytest

from cn_contract import domain as d
from tests.helpers.trademark_triage import KINDS, draft_for, manifest_for


def module():
    name = 'cn_contract.assistant.trademark_triage'
    assert importlib.util.find_spec(name) is not None, 'The trademark triage implementation is missing.'
    return importlib.import_module(name)


def fixture(question='请做商标侵权初筛。'):
    mod, manifest = module(), manifest_for(question)
    snapshot = mod.select_method(manifest.workflow, manifest.question)
    assert snapshot is not None
    return mod, manifest.model_copy(update={'trademark_triage': snapshot})


def test_all_eight_factors_required_and_missing_side_is_not_exoneration():
    mod, manifest = fixture()
    value = draft_for(manifest)
    result = mod.candidate(value, manifest)
    assert tuple(f.kind for f in result.trademark_triage.factors) == KINDS
    assert '暂无已引述线索' in result.text and '不能认定不存在' in result.text
    assert set(result.citations) == {q['source_id'] for q in value['quotes']}
    value['factors'].pop()
    with pytest.raises(ValueError):
        mod.candidate(value, manifest)


@pytest.mark.parametrize('workflow,question,selected', [
    ('case', '请做商标侵权初筛。', True), ('case', '请做商标分析。', True),
    ('case', '请做侵权因素分析，权利类型为商标。', True),
    ('case', '不要商标侵权初筛，只整理材料。', False),
    ('case', '不做商标初筛。', False),
    ('case', '请做商标侵权初筛；现在取消商标初筛。', False),
    ('case', '“请做商标分析”是对方说的话。', False),
    ('case', '客户说请做商标分析。', False),
    ('case', '如果收到材料再做商标分析。', False),
    ('case', '只保存材料，暂不分析商标。', False),
    ('case', '请整理时间线。', False), ('contract', '请做商标侵权初筛。', False),
    ('case', '不要专利侵权初筛，请做商标侵权初筛。', True),
    ('case', '请做商标侵权初筛，不需要专利侵权初筛。', True),
])
def test_only_current_explicit_nonnegated_trademark_requests_select(workflow, question, selected):
    assert (module().select_method(workflow, question) is not None) == selected


@pytest.mark.parametrize('question', [
    '请分析专利侵权。', '请做著作权侵权初筛。', '请做商业秘密侵权初筛。',
    '请做知识产权初筛。', '请做侵权因素分析，权利类型不明。',
    '请做知识产权分析，目前不确定是否属于商标。',
    '请做商标与专利侵权初筛。', '请做商标侵权初筛和著作权分析。',
    '请做商标侵权初筛，同时做刑事证据分析。',
])
def test_other_mixed_or_unclear_rights_are_explicitly_unsupported(question):
    with pytest.raises(ValueError, match='IP_SCOPE_UNSUPPORTED'):
        module().select_method('case', question)


@pytest.mark.parametrize('field,value', [
    ('method_sha256', 'f'*64), ('source_reference', 'https://example.invalid/changed'),
    ('license_notice', '许可不明'), ('method_id', 'trademark-triage-v99'), ('right_type', 'patent'),
])
def test_system_rejects_changed_fixed_method_metadata(field, value):
    mod, manifest = fixture()
    snapshot = manifest.trademark_triage.model_copy(update={field:value})
    with pytest.raises(ValueError):
        mod.method_system(snapshot)


def test_snapshot_revalidates_current_question_and_other_method_exclusion():
    mod, manifest = fixture()
    mod.validate_snapshot(manifest)
    assert mod.method_system(manifest.trademark_triage)
    for altered in (manifest.model_copy(update={'question':'不要商标初筛。'}),
            manifest.model_copy(update={'workflow':'contract'}),
            manifest.model_copy(update={'case_method':d.CaseMethodSnapshot(
                method_id='case-evidence-v1', method_sha256='a'*64)})):
        with pytest.raises(ValueError):
            mod.validate_snapshot(altered)


@pytest.mark.parametrize('mutation', ['factor_duplicate', 'factor_order', 'quote_duplicate', 'quote_unused',
    'quote_unknown', 'quote_changed', 'quote_offset', 'message_quote', 'unknown_id', 'duplicate_ref',
    'empty_refs', 'inline_borrow', 'unresolved_inline', 'gap_inline', 'missing_unresolved', 'approved', 'conclusion'])
def test_candidate_rejects_incomplete_or_unbound_evidence(mutation):
    mod, manifest = fixture()
    value = draft_for(manifest)
    if mutation == 'factor_duplicate': value['factors'][1]['kind'] = 'rights_basis'
    elif mutation == 'factor_order': value['factors'][0], value['factors'][1] = value['factors'][1], value['factors'][0]
    elif mutation == 'quote_duplicate': value['quotes'][1]['id'] = 'q1'
    elif mutation == 'quote_unused': value['quotes'].append(dict(value['quotes'][0], id='extra'))
    elif mutation == 'quote_unknown': value['quotes'][0]['source_id'] = 'c'*64
    elif mutation == 'quote_changed': value['quotes'][0]['exact_quote'] = '改写后的文本'
    elif mutation == 'quote_offset': value['quotes'][0]['start'] = 1
    elif mutation == 'message_quote':
        source = manifest.sources[0]
        value['quotes'][0].update(source_id=source.source_id, start=0,
            end=len(source.reference.quote), exact_quote=source.reference.quote)
    elif mutation == 'unknown_id': value['factors'][0]['holder'][0]['quote_ids'] = ['absent']
    elif mutation == 'duplicate_ref': value['factors'][0]['holder'][0]['quote_ids'] = ['q1', 'q1']
    elif mutation == 'empty_refs': value['factors'][0]['holder'][0]['quote_ids'] = []
    elif mutation == 'inline_borrow': value['factors'][0]['holder'][0]['text'] += '[' + value['quotes'][1]['source_id'] + ']'
    elif mutation == 'unresolved_inline': value['factors'][0]['unresolved'] = ['待核[' + value['quotes'][0]['source_id'] + ']']
    elif mutation == 'gap_inline': value['gaps'] = ['待核[' + value['quotes'][0]['source_id'] + ']']
    elif mutation == 'missing_unresolved': value['factors'][0]['unresolved'] = []
    elif mutation == 'approved': value['approved'] = True
    elif mutation == 'conclusion': value['conclusion'] = '侵权成立'
    with pytest.raises(ValueError):
        mod.candidate(value, manifest)


def test_current_quote_allows_own_inline_source_but_not_another_observations_source():
    mod, manifest = fixture()
    value = draft_for(manifest)
    value['factors'][0]['holder'][0]['text'] += '[' + value['quotes'][0]['source_id'] + ']'
    assert mod.candidate(value, manifest).trademark_triage is not None


def test_host_cautions_provenance_and_unread_parts_are_not_model_controlled():
    mod, manifest = fixture()
    material = manifest.materials[0].model_copy(update={'reading_status':'partial',
        'unread_parts':('图片1',), 'quality_issues':('段落次序待核',)})
    manifest = manifest.model_copy(update={'materials':(material,)})
    result = mod.candidate(draft_for(manifest), manifest)
    for text in ('当事人地位', '权属及登记', '许可范围', '使用行为', '地域与管辖', '时效起算',
            '不默认我方身份或中国管辖', '不自动计算期限', '同类目不直接等于商品类似',
            '无实际混淆材料不等于无混淆', '图片/图形及URL链接内容未读取', '驰名保护及虚假宣传',
            '自由文本推理质量已核验', '未读部分：图片1', '解析质量待核：段落次序待核',
            '独立虚构商标材料.docx', '解析版本1', mod.UPSTREAM, 'Apache-2.0'):
        assert text in result.text
    assert all(label in result.text for label in mod.FACTORS.values())


def test_new_optional_fields_do_not_change_legacy_manifest_or_candidate_bytes():
    manifest = manifest_for('请整理材料。')
    assert 'trademark_triage' not in manifest.model_dump(mode='json')
    candidate = d.MainMaterialCandidate(text='旧候选', citations=(manifest.sources[1].source_id,))
    assert 'trademark_triage' not in candidate.model_dump(mode='json')


def test_dto_rejects_trademark_and_existing_methods_together():
    mod, manifest = fixture()
    value = manifest.model_dump(mode='python')
    value['case_method'] = {'method_id':'case-evidence-v1', 'method_sha256':'a'*64}
    with pytest.raises(ValueError, match='TRADEMARK_METHOD_WORKFLOW_INVALID'):
        d.MainMaterialManifest.model_validate(value)
    candidate = mod.candidate(draft_for(manifest), manifest).model_dump(mode='python')
    candidate['case_evidence'] = dict(format_version='case-evidence-v1', quotes=candidate['trademark_triage']['quotes'],
        statements=[dict(kind='source_statement', text='旧方法观察', support=['q1', 'q2'], opposing=[], unresolved=[])],
        timeline=[], gaps=['待核'])
    with pytest.raises(ValueError, match='TRADEMARK_OUTPUT_INVALID'):
        d.MainMaterialCandidate.model_validate(candidate)
