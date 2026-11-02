"""Criminal method boundaries on fictional material, without a model call."""
import importlib
import importlib.util

import pytest

from tests.helpers.criminal_analysis import draft_for, manifest_for


def module():
    name = 'cn_contract.assistant.criminal_analysis'
    assert importlib.util.find_spec(name) is not None, 'The criminal method implementation is missing.'
    return importlib.import_module(name)


def fixture(question='请分析刑事证据并提出辩护策略。\n当前阶段：审查起诉'):
    mod, manifest = module(), manifest_for(question)
    snapshot = mod.select_method(manifest.workflow, manifest.question, manifest.sources)
    return mod, manifest.model_copy(update={'criminal_analysis':snapshot})


@pytest.mark.parametrize('workflow,question,selected', [
    ('case', '请做刑事证据分析。', True), ('case', '请提出刑事辩护策略。', True),
    ('case', '不要做刑事分析，只整理民事材料。', False),
    ('case', '不用生成文书，请做刑事证据分析。', True),
    ('case', '请整理民事时间线。', False), ('court', '请做刑事辩护分析。', False),
])
def test_only_explicit_nonnegated_case_requests_select_criminal_method(workflow, question, selected):
    mod, manifest = module(), manifest_for(question)
    assert (mod.select_method(workflow, question, manifest.sources) is not None) == selected


@pytest.mark.parametrize('declaration,expected', [
    ('当前阶段：侦查', 'investigation'), ('当前阶段：审查起诉', 'prosecution'),
    ('当前阶段：审判', 'trial'), ('', 'unknown'),
    ('当前阶段：侦查\n当前阶段：审判', 'unknown'),
    ('对方称当前阶段：审查起诉', 'unknown'), ('如果当前阶段：审查起诉', 'unknown'),
    ('“当前阶段：审查起诉”', 'unknown'), ('当前阶段：审查起诉？', 'unknown'),
])
def test_stage_is_an_independent_current_user_declaration(declaration, expected):
    mod, manifest = fixture('请做刑事分析。\n' + declaration)
    snapshot = manifest.criminal_analysis
    assert snapshot.stage == expected
    assert snapshot.stage_source_id == (manifest.sources[0].source_id if expected != 'unknown' else None)
    assert snapshot.material_policy == 'synthetic-only-v1'
    assert tuple(s.method_id for s in snapshot.method_sources) == ('case_analysis', 'defense_strategy')


def test_attachment_stage_or_missing_message_cannot_supply_procedural_stage():
    mod = module()
    manifest = manifest_for('请做刑事分析。', texts=('当前阶段：审查起诉', '虚构说法乙', '虚构说法丙'))
    assert mod.select_method('case', manifest.question, manifest.sources).stage == 'unknown'
    question = '请做刑事分析。\n当前阶段：审查起诉'
    manifest = manifest_for(question)
    assert mod.select_method('case', question, manifest.sources[1:]).stage == 'unknown'


def test_valid_result_preserves_evidence_categories_and_host_cautions():
    mod, manifest = fixture()
    result = mod.candidate(draft_for(manifest), manifest)
    assert result.criminal_analysis is not None
    assert set(result.citations) == {s.source_id for s in manifest.sources[1:]}
    for label in ('定罪证据', '量刑证据', '真实性矛盾', '尚未排非', '不承诺', '用户陈述', '未核验'):
        assert label in result.text
    assert '独立虚构刑事材料.docx' in result.text and '解析版本1' in result.text
    assert all(s.source_reference in result.text for s in manifest.criminal_analysis.method_sources)


@pytest.mark.parametrize('mutation', ['restitution_conviction', 'sentencing_element', 'authenticity_no_opposing',
    'unknown_quote', 'altered_quote', 'wrong_offset', 'unknown_evidence', 'duplicate_evidence',
    'duplicate_quote', 'unused_quote', 'message_evidence', 'inline_borrow', 'timeline_date',
    'timeline_duplicate', 'model_stage', 'approved'])
def test_invalid_evidence_structure_is_rejected(mutation):
    mod, manifest = fixture()
    value = draft_for(manifest)
    if mutation == 'restitution_conviction': value['evidence'][2]['category'] = 'conviction'
    elif mutation == 'sentencing_element': value['elements'][0]['evidence_ids'] = ['e3']
    elif mutation == 'authenticity_no_opposing': value['evidence'][1]['opposing'] = []
    elif mutation == 'unknown_quote': value['evidence'][0]['support'] = ['absent']
    elif mutation == 'altered_quote': value['quotes'][0]['exact_quote'] = '被改写的说法'
    elif mutation == 'wrong_offset': value['quotes'][0]['start'] = 1
    elif mutation == 'unknown_evidence': value['strategies'][0]['evidence_ids'] = ['absent']
    elif mutation == 'duplicate_evidence': value['evidence'][1]['id'] = 'e1'
    elif mutation == 'duplicate_quote': value['quotes'][1]['id'] = 'q1'
    elif mutation == 'unused_quote': value['quotes'].append(dict(value['quotes'][0], id='extra'))
    elif mutation == 'message_evidence':
        source = manifest.sources[0]
        value['quotes'][0].update(source_id=source.source_id, start=0, end=len(source.reference.quote), exact_quote=source.reference.quote)
    elif mutation == 'inline_borrow': value['evidence'][0]['claim'] += '[' + value['quotes'][2]['source_id'] + ']'
    elif mutation == 'timeline_date': value['timeline'][0]['raw_date'] = '2026年10月30日'
    elif mutation == 'timeline_duplicate': value['timeline'] *= 2
    elif mutation == 'model_stage': value['stage'] = 'prosecution'
    elif mutation == 'approved': value['approved'] = True
    with pytest.raises(ValueError): mod.candidate(value, manifest)


@pytest.mark.parametrize('declaration', ['', '当前阶段：侦查', '当前阶段：审判'])
def test_non_prosecution_strategy_requires_declared_prosecution_stage(declaration):
    mod, manifest = fixture('请做刑事分析。\n' + declaration)
    value = draft_for(manifest)
    value['strategies'][0]['kind'] = 'non_prosecution'
    with pytest.raises(ValueError): mod.candidate(value, manifest)


@pytest.mark.parametrize('field,value', [('stage', 'trial'), ('stage_source_id', 'f'*64), ('method_sha256', 'f'*64)])
def test_snapshot_cannot_change_stage_or_method_after_selection(field, value):
    mod, manifest = fixture()
    changed = manifest.model_copy(update={'criminal_analysis':manifest.criminal_analysis.model_copy(update={field:value})})
    with pytest.raises(ValueError): mod.validate_snapshot(changed)


def test_fixed_method_source_and_license_cannot_be_substituted():
    mod, manifest = fixture()
    snapshot = manifest.criminal_analysis
    source = snapshot.method_sources[0].model_copy(update={'source_reference':'https://example.invalid/untrusted'})
    with pytest.raises(ValueError): mod.method_system(snapshot.model_copy(update={'method_sources':(source, *snapshot.method_sources[1:])}))


def test_partial_material_and_unread_parts_are_always_rendered():
    mod, manifest = fixture()
    material = manifest.materials[0].model_copy(update={'reading_status':'partial', 'unread_parts':('未解析附页',),
        'quality_issues':('原文缺页待核',)})
    manifest = manifest.model_copy(update={'materials':(material,)})
    result = mod.candidate(draft_for(manifest), manifest)
    assert '仅部分可读' in result.text and '未解析附页' in result.text and '原文缺页待核' in result.text


@pytest.mark.parametrize('question', [
    '请做刑事证据分析，不需要辩护策略。',
    '不需要辩护策略，请做刑事证据分析。',
    '请做刑事证据分析，不要辩护思路。',
])
def test_analysis_remains_selected_when_defense_deliverable_is_declined(question):
    mod, manifest = fixture(question)
    assert manifest.criminal_analysis is not None
    assert tuple(s.method_id for s in manifest.criminal_analysis.method_sources) == ('case_analysis',)
    value = draft_for(manifest)
    assert value['elements'] == [] and value['strategies'] == []
    result = mod.candidate(value, manifest)
    assert result.criminal_analysis.evidence
    assert '构成要件候选：' not in result.text and '不起诉策略选项（待审）' not in result.text
    assert '【defense_strategy】' not in mod.method_system(manifest.criminal_analysis)


@pytest.mark.parametrize('field', ['elements', 'strategies'])
def test_analysis_only_output_cannot_restore_declined_defense_sections(field):
    mod, manifest = fixture('不需要辩护策略，请做刑事证据分析。')
    assert manifest.criminal_analysis is not None
    _, complete = fixture()
    value = draft_for(complete)
    value['elements'] = []
    value['strategies'] = []
    value[field] = draft_for(complete)[field]
    # Keep the scoped request's source identities, so rejection is about scope.
    value['quotes'] = draft_for(manifest)['quotes']
    with pytest.raises(ValueError, match='CRIMINAL_SCOPE_INVALID'):
        mod.candidate(value, manifest)


@pytest.mark.parametrize('field', ['elements', 'strategies'])
def test_selected_defense_method_still_requires_both_deliverables(field):
    mod, manifest = fixture()
    value = draft_for(manifest)
    value[field] = []
    with pytest.raises(ValueError): mod.candidate(value, manifest)


def test_later_positive_defense_request_restores_the_full_method_set():
    mod, manifest = fixture('请做刑事证据分析，不需要辩护策略。\n现在需要辩护策略。')
    assert tuple(s.method_id for s in manifest.criminal_analysis.method_sources) == ('case_analysis', 'defense_strategy')
    assert mod.candidate(draft_for(manifest), manifest).criminal_analysis.strategies
