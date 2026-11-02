"""Mechanical support controls are not proof of a model's role interpretation."""
from copy import deepcopy
import pytest
from cn_contract import domain as d
from cn_contract.assistant import trademark_triage as method, material_codec as codec
from tests.helpers.trademark_support import manifest, draft, span
from tests.unit.test_contract_live_method import sample
from tests.helpers.trademark_triage import manifest_for, draft_for


def test_explicit_support_method_roundtrips_without_changing_legacy_default():
    m = manifest()
    assert method.select_method('case', m.question).method_id == 'trademark-triage-v5'
    _, selection, config = sample('case')
    basis = codec.build_basis(selection, m, config)
    assert codec.rebuild_basis(basis, config) == basis
    result = method.candidate(draft(m), m)
    restored = d.MainMaterialCandidate.model_validate_json(result.model_dump_json())
    assert codec.validate_manifest_candidate(restored, m) == result
    assert result.trademark_triage.format_version == 'trademark-triage-v3'
    assert '陈述者：未知' in result.text
    assert '事件时间：2022年' in result.text
    assert '转述时间：2025年3月' in result.text
    assert '成文时间：未知' in result.text
    assert '角色由模型提取，尚未核实' in result.text
    for q in draft(m)['quotes']:
        assert q['exact_quote'] in result.text
    assert result.text.count('引文材料：独立虚构商标材料.docx') == 2


@pytest.mark.parametrize('damage', [
    'duplicate_statement', 'duplicate_statement_quote', 'unknown_statement_quote',
    'unused_quote', 'unused_statement', 'span_wrong_quote', 'span_outside_quote',
    'span_empty', 'span_whitespace', 'duplicate_observation_statement', 'unknown_observation_statement',
    'duplicate_dependency', 'unlisted_dependency', 'recorded_unknown_speaker',
    'recorded_unknown_record_time', 'inference_no_dependency', 'comparison_single',
    'comparison_unknown_object', 'comparison_no_actor_dependency',
    'observation_foreign_inline', 'unresolved_inline', 'gap_inline',
])
def test_rejects_invalid_declared_support(damage):
    m = manifest(); raw = draft(m)
    method.candidate(raw, m)
    o = raw['factors'][0]['neutral'][0]
    dep = dict(statement_id='s2', slot='speaker')
    if damage == 'duplicate_statement': raw['source_statements'].append(deepcopy(raw['source_statements'][0]))
    elif damage == 'duplicate_statement_quote': raw['source_statements'][0]['quote_ids'] *= 2
    elif damage == 'unknown_statement_quote': raw['source_statements'][0]['quote_ids'] = ['q99']
    elif damage == 'unused_quote': raw['quotes'].append(dict(raw['quotes'][0], id='q99'))
    elif damage == 'unused_statement': raw['source_statements'].append(dict(raw['source_statements'][0], id='s99'))
    elif damage == 'span_wrong_quote': raw['source_statements'][0]['speaker'] = span(raw, 'q2', '虚构职员')
    elif damage == 'span_outside_quote': raw['source_statements'][1]['speaker']['end'] = 999
    elif damage == 'span_empty': raw['source_statements'][1]['speaker'].update(start=4, end=4)
    elif damage == 'span_whitespace':
        # An exact one-character whitespace span is not a role value.
        q = raw['quotes'][0]; q['start'] = 4; q['end'] = 5; q['exact_quote'] = ' '
        mraw = m.model_dump(mode='python')
        ref = mraw['sources'][1]['reference']
        ref['anchor']['quote'] = ref['anchor']['quote'][:4] + ' ' + ref['anchor']['quote'][5:]
        from cn_contract.assistant.providers.policy import sha, encoded
        ref['anchor']['quote_sha256'] = sha(ref['anchor']['quote'])
        q['source_id'] = mraw['sources'][1]['source_id'] = sha(encoded(d.ProfileDocumentRef.model_validate(ref)))
        m = d.MainMaterialManifest.model_validate(mraw)
        raw['source_statements'][0]['speaker'] = dict(quote_id='q1', start=4, end=5)
    elif damage == 'duplicate_observation_statement': o['statement_ids'] *= 2
    elif damage == 'unknown_observation_statement': o['statement_ids'] = ['s99']
    elif damage == 'duplicate_dependency': o['dependencies'] = [dep, dep]
    elif damage == 'unlisted_dependency':
        o['statement_ids'] = ['s1']; o['dependencies'] = [dep]
    elif damage == 'recorded_unknown_speaker': o['dependencies'] = [dict(statement_id='s1', slot='speaker')]
    elif damage == 'recorded_unknown_record_time': o['dependencies'] = [dict(statement_id='s2', slot='record_time')]
    elif damage == 'inference_no_dependency': o['relation'] = 'conditional_inference'
    elif damage == 'comparison_single':
        o.update(relation='comparison', statement_ids=['s2'], dependencies=[dep])
    elif damage.startswith('comparison_'):
        o.update(relation='comparison', dependencies=[dict(statement_id=s, slot=k)
            for s in ('s1', 's2') for k in ('actor', 'object')])
        if damage == 'comparison_no_actor_dependency':
            o['dependencies'] = [dict(statement_id=s, slot='object') for s in ('s1', 's2')]
    elif damage == 'observation_foreign_inline': o['text'] += '[' + 'f'*64 + ']'
    elif damage == 'unresolved_inline': raw['factors'][0]['unresolved'] = ['[' + raw['quotes'][0]['source_id'] + ']']
    elif damage == 'gap_inline': raw['gaps'] = ['[' + raw['quotes'][0]['source_id'] + ']']
    with pytest.raises(ValueError):
        method.candidate(raw, m)


def test_unknown_dependency_is_explicitly_conditioned_and_time_slots_stay_distinct():
    m = manifest(); raw = draft(m)
    o = raw['factors'][0]['neutral'][0]
    o.update(relation='conditional_inference', dependencies=[
        dict(statement_id='s1', slot='speaker'), dict(statement_id='s2', slot='record_time'),
        dict(statement_id='s2', slot='report_time')])
    result = method.candidate(raw, m)
    assert '条件推断：' in result.text
    assert '未知前提（未核实，不能据此确认结论）：s1 陈述者' in result.text
    assert '未知前提（未核实，不能据此确认结论）：s2 成文时间' in result.text
    assert '声明依赖：s2 转述时间' in result.text


def test_exact_seal_span_mislabel_remains_a_visible_semantic_risk():
    m = manifest(); raw = draft(m)
    raw['source_statements'][0]['speaker'] = span(raw, 'q1', '澄原公司')
    raw['factors'][0]['neutral'][0]['dependencies'] = [dict(statement_id='s1', slot='speaker')]
    result = method.candidate(raw, m)
    # This intentional characterization must not be counted as a legal-quality PASS.
    assert '陈述者：澄原公司' in result.text
    assert '角色由模型提取，尚未核实' in result.text


def comparable():
    m = manifest()
    m = manifest_for(texts=('虚构记载称澄原公司使用青禾牌，作者与形成时间未核。',
        m.sources[2].reference.anchor.quote)).model_copy(update={'trademark_triage': m.trademark_triage})
    raw = draft(m)
    raw['source_statements'][0].update(actor=span(raw, 'q1', '澄原公司'), object=span(raw, 'q1', '青禾牌'))
    o = raw['factors'][0]['neutral'][0]
    o.update(text='两条记载字面上对象与行为人相同，但不证明同一事实或矛盾。',
        relation='comparison', dependencies=[dict(statement_id=s, slot=k)
            for s in ('s1', 's2') for k in ('actor', 'object')])
    return m, raw


@pytest.mark.parametrize('slot', ['actor', 'object'])
def test_different_nonempty_comparison_operands_are_rejected(slot):
    m, raw = comparable()
    assert '并列比较' in method.candidate(raw, m).text
    raw['source_statements'][0][slot] = span(raw, 'q1', '虚构记载')
    with pytest.raises(ValueError, match='TRADEMARK_SUPPORT_INVALID'):
        method.candidate(raw, m)


def test_comparison_cannot_omit_actor_dependency_even_when_role_is_known():
    m, raw = comparable()
    method.candidate(raw, m)
    raw['factors'][0]['neutral'][0]['dependencies'] = [
        dict(statement_id=s, slot='object') for s in ('s1', 's2')]
    with pytest.raises(ValueError, match='TRADEMARK_SUPPORT_INVALID'):
        method.candidate(raw, m)


def test_source_span_uses_absolute_source_offset_and_cannot_escape_its_quote():
    m, raw = comparable()
    q = raw['quotes'][0]
    q.update(start=5, exact_quote=q['exact_quote'][5:])
    result = method.candidate(raw, m)
    assert '行为人：澄原公司' in result.text
    raw['source_statements'][0]['actor']['start'] = 0
    with pytest.raises(ValueError, match='TRADEMARK_SUPPORT_INVALID'):
        method.candidate(raw, m)


@pytest.mark.parametrize('text', [' ', '长'*201])
def test_exact_but_blank_or_overlong_role_value_is_rejected(text):
    original = manifest()
    m = manifest_for(texts=('材料前缀' + text + '材料后缀', original.sources[2].reference.anchor.quote)
        ).model_copy(update={'trademark_triage': original.trademark_triage})
    raw = draft(m)
    method.candidate(raw, m)
    raw['source_statements'][0]['speaker'] = span(raw, 'q1', text)
    with pytest.raises(ValueError, match='TRADEMARK_SUPPORT_INVALID'):
        method.candidate(raw, m)


@pytest.mark.parametrize('damage', ['missing_slot', 'extra_value', 'old_format', 'old_method', 'borrow_hash',
    'unknown_slot', 'wrong_factor_order', 'unknown_relation'])
def test_schema_version_and_snapshot_cannot_be_mixed(damage):
    m = manifest(); raw = draft(m); method.candidate(raw, m)
    if damage == 'missing_slot': del raw['source_statements'][0]['speaker']
    elif damage == 'extra_value': raw['source_statements'][1]['speaker']['value'] = '冒名'
    elif damage == 'old_format': raw = draft_for(m)
    elif damage == 'old_method':
        m = m.model_copy(update={'trademark_triage': method.select_method('case', m.question)})
    elif damage == 'borrow_hash':
        old = method.select_method('case', m.question)
        m = m.model_copy(update={'trademark_triage': old.model_copy(update={'method_id':'trademark-triage-v6'})})
    elif damage == 'unknown_slot':
        raw['factors'][0]['neutral'][0]['dependencies'] = [dict(statement_id='s2', slot='any_time')]
    elif damage == 'wrong_factor_order': raw['factors'].reverse()
    elif damage == 'unknown_relation': raw['factors'][0]['neutral'][0]['relation'] = 'proven'
    with pytest.raises(ValueError):
        method.candidate(raw, m)


@pytest.mark.parametrize('question', ['暂时不分析商标，只接收材料。', '若以后需要商标初筛，再联系我。',
    '“请做商标初筛”只是原文。', '【请做商标初筛】只是原文。暂时不分析，只收材料。'])
def test_v6_preserves_current_instruction_hold(question):
    assert method.select_method('case', question, method_id='trademark-triage-v6') is None


def test_v6_labelled_source_cannot_fall_back_to_case_model():
    with pytest.raises(ValueError, match='MATERIAL_INSTRUCTION_CONFLICT'):
        method.select_method('case', '【请做商标初筛】仅是引用。', method_id='trademark-triage-v6')


def test_one_source_statement_cannot_merge_roles_from_different_paragraphs():
    m = manifest(); raw = draft(m)
    method.candidate(raw, m)
    raw['source_statements'][0]['quote_ids'] = ['q1', 'q2']
    raw['source_statements'][0]['report_time'] = span(raw, 'q2', '2025年3月')
    with pytest.raises(ValueError, match='TRADEMARK_SUPPORT_INVALID'):
        method.candidate(raw, m)


def test_recorded_and_comparison_disclose_model_interpretation_at_point_of_use():
    m = manifest()
    assert '材料记载（模型归纳，非事实认定）' in method.candidate(draft(m), m).text
    m, raw = comparable()
    assert '文字相同不证明同一主体、对象或存在矛盾' in method.candidate(raw, m).text


def test_unknown_premise_is_not_rendered_as_a_false_fact():
    m = manifest(); raw = draft(m)
    raw['factors'][0]['neutral'][0].update(relation='conditional_inference',
        dependencies=[dict(statement_id='s1', slot='speaker')])
    text = method.candidate(raw, m).text
    assert '查实前不成立' not in text
    assert '未知前提（未核实，不能据此确认结论）：s1 陈述者' in text
