"""Source-bound registers exercise real local CaseStore; no model or network."""
import copy
import importlib.util

import pytest
from business_store import CaseStore
from reader import parse


def save(*args, **kwargs):
    assert importlib.util.find_spec('source_bound_registers'), 'source-bound register saver is missing'
    from source_bound_registers import save_source_bound_register
    return save_source_bound_register(*args, **kwargs)


@pytest.fixture
def world(tmp_path):
    cases = CaseStore(tmp_path)
    cid = cases.create('来源约束合成案')['id']
    source = tmp_path / '来源.txt'
    source.write_text('议题一已表决：赞成4票、反对1票、弃权0票。议题二未提供表决记录。\n'
                      '经营层已决定不反馈；材料未显示报告提交记录。\n'
                      '专利仅有受理材料，未提供授权公告。商标尚未申请。\n'
                      '境内商标证载期至2028-06-30；内部表预计2030到期，未给依据。', encoding='utf-8')
    cases.store.register(source.name)
    parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    view = cases.read_material(cid, source.name)
    ref = {'path': source.name, 'sha256': view['sha256'], 'chunk': 0,
           'quote': '议题一已表决：赞成4票、反对1票、弃权0票。'}
    return cases, cid, source, ref


@pytest.mark.parametrize(('domain', 'field', 'quote'), [
    ('corporate', 'votes', '议题一已表决：赞成4票、反对1票、弃权0票。'),
    ('compliance', 'decision', '经营层已决定不反馈；材料未显示报告提交记录。'),
    ('ip', 'status', '专利仅有受理材料，未提供授权公告。商标尚未申请。'),
])
def test_records_known_values_verbatim_without_converting_missing_records_to_no_event(world, domain, field, quote):
    cases, cid, source, ref = world
    ref['quote'] = quote
    result = save(cases, cid, domain, [{'field': field, 'citation': ref}])
    note = CaseStore(cases.root).read_note(cid, result['id'], limit=16000)
    assert result['saved'] and result['legal_verified'] is False
    assert quote in note['content']
    assert '报告尚未提交' not in note['content']
    assert '议题二尚不存在的表决结果' not in note['content']
    assert '已受理、尚未授权' not in note['content']
    assert note['citations'][0]['version'] == 1
    assert note['citations'][0]['sha256'] == ref['sha256']
    assert note['review_status'] == 'unverified'


def test_short_excerpt_cannot_remove_its_negating_context(world):
    cases, cid, source, ref = world
    ref['quote'] = '授权公告'
    result = save(cases, cid, 'ip', [{'field': 'status', 'citation': ref}])
    row = result['entries'][0]
    assert row['quote'] == '授权公告'
    assert '未提供授权公告' in row['context']
    assert '未提供授权公告' in cases.read_note(cid, result['id'], limit=16000)['content']
    assert row['actual_status'] != '已授权'


@pytest.mark.parametrize('extra', [{'actual_status': '未提交'}, {'effective': True},
                                  {'observed': '已决定'}, {'content': '债务拟发生'}])
def test_model_cannot_supply_an_actual_event_or_effectiveness_field(world, extra):
    cases, cid, source, ref = world
    with pytest.raises(ValueError):
        save(cases, cid, 'corporate', [{'field': 'decision', 'citation': ref, **extra}])
    assert cases.get(cid)['total_notes'] == 0


def test_freeform_field_cannot_inject_company_type_or_future_debt(world):
    cases, cid, source, ref = world
    with pytest.raises(ValueError):
        save(cases, cid, 'corporate', [{'field': 'XX有限公司之间拟发生的债务', 'citation': ref}])


@pytest.mark.parametrize('mutation', ['quote', 'hash', 'chunk', 'other_case', 'unlinked'])
def test_invalid_evidence_rejects_whole_batch_without_saving(world, mutation):
    cases, cid, source, ref = world
    bad = copy.deepcopy(ref)
    if mutation == 'quote': bad['quote'] = '报告已提交'
    if mutation == 'hash': bad['sha256'] = 'f' * 64
    if mutation == 'chunk': bad['chunk'] = 999
    if mutation == 'other_case': bad['case_id'] = cases.create('其他案件')['id']
    if mutation == 'unlinked':
        other = cases.root / '其他案.txt'
        other.write_text(ref['quote'], encoding='utf-8')
        cases.store.register(other.name)
        parse(cases.store, other.name)
        other_id = cases.create('另案')['id']
        cases.link_materials(other_id, [other.name])
        bad.update(path=other.name, sha256=cases.read_material(other_id, other.name)['sha256'])
    with pytest.raises(ValueError):
        save(cases, cid, 'corporate', [{'field': 'votes', 'citation': ref},
                                     {'field': 'decision', 'citation': bad}])
    assert cases.get(cid)['total_notes'] == 0


def test_changed_original_is_rejected_even_when_quote_still_exists(world):
    cases, cid, source, ref = world
    source.write_text(source.read_text(encoding='utf-8') + '\n补充。', encoding='utf-8')
    with pytest.raises(ValueError):
        save(cases, cid, 'corporate', [{'field': 'votes', 'citation': ref}])
    assert cases.get(cid)['total_notes'] == 0


def test_caller_cannot_launder_verified_status_or_supply_unbound_quote(world):
    cases, cid, source, ref = world
    for key, value in [('status', 'matched'), ('version', 9), ('sha256', None)]:
        bad = {**ref, key: value}
        with pytest.raises(ValueError):
            save(cases, cid, 'corporate', [{'field': 'votes', 'citation': bad}])


def test_idempotent_save_and_append_only_correction_retain_source_versions(world):
    cases, cid, source, ref = world
    entries = [{'field': 'votes', 'citation': ref}]
    first = save(cases, cid, 'corporate', entries, request_id='first')
    again = save(cases, cid, 'corporate', entries, request_id='first')
    assert first['id'] == again['id']
    source.write_text('更正记录：赞成5票、反对0票、弃权0票。', encoding='utf-8')
    cases.store.register(source.name)
    parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    ref.update(sha256=cases.read_material(cid, source.name)['sha256'], quote=source.read_text(encoding='utf-8'))
    second = save(cases, cid, 'corporate', entries, request_id='second', supersedes=first['id'])
    assert cases.get(cid)['notes'][0]['id'] == second['id']
    assert cases.read_note(cid, first['id'])['citations'][0]['version'] == 1
    assert cases.read_note(cid, second['id'])['citations'][0]['version'] == 2


def test_ip_card_has_application_transition_basis_without_assigning_asset_term(world):
    cases, cid, source, ref = world
    ref['quote'] = '境内商标证载期至2028-06-30；内部表预计2030到期，未给依据。'
    result = save(cases, cid, 'ip', [{'field': 'certificate_term', 'citation': ref}])
    card = result['rule_cards'][0]
    assert card['transition_basis'] == 'application_date'
    assert card['applies_before'] == '2021-06-01'
    assert card['pre_transition_years'] == 10
    assert card['applied_to_asset'] is False
    assert card['jurisdiction'] == '中国'
    assert card['official_source'].startswith('https://www.cnipa.gov.cn/')
    body = cases.read_note(cid, result['id'], limit=16000)['content']
    assert ref['quote'] in body
    assert '授权时适用' not in body
    assert result['entries'][0].get('calculated_expiry') is None


def test_generated_draft_cannot_become_an_independent_source(world):
    cases, cid, source, ref = world
    folder = cases.root / 'drafts'
    folder.mkdir()
    draft = folder / '模型结论.txt'
    draft.write_text(ref['quote'], encoding='utf-8')
    cases.store.register('drafts/模型结论.txt')
    parse(cases.store, 'drafts/模型结论.txt')
    cases.link_materials(cid, ['drafts/模型结论.txt'])
    ref.update(path='drafts/模型结论.txt', sha256=cases.read_material(cid, 'drafts/模型结论.txt')['sha256'])
    with pytest.raises(ValueError):
        save(cases, cid, 'corporate', [{'field': 'votes', 'citation': ref}])


def test_source_change_between_validation_and_insert_rolls_back_real_note(world, monkeypatch):
    cases, cid, source, ref = world
    original = cases._add_note
    def change_then_save(*args, **kwargs):
        source.write_text('替换的新材料。', encoding='utf-8')
        return original(*args, **kwargs)
    monkeypatch.setattr(cases, '_add_note', change_then_save)
    with pytest.raises(ValueError):
        save(cases, cid, 'corporate', [{'field': 'votes', 'citation': ref}])
    assert cases.get(cid)['total_notes'] == 0


def test_correction_conflict_is_not_reported_as_saved(world):
    cases, cid, source, ref = world
    entries = [{'field': 'votes', 'citation': ref}]
    first = save(cases, cid, 'corporate', entries)
    second = save(cases, cid, 'corporate', entries, supersedes=first['id'])
    conflict = save(cases, cid, 'corporate', entries, supersedes=first['id'])
    assert not conflict['saved'] and conflict['recorded'] is False
    assert cases.get(cid)['notes'][0]['id'] == second['id']
    assert len(cases.get(cid, include_history=True)['notes']) == 2


def test_misclassified_voting_quote_does_not_activate_patent_rule_or_infer_filing_date(world):
    cases, cid, source, ref = world
    result = save(cases, cid, 'ip', [{'field': 'filing_date', 'citation': ref}])
    row = result['entries'][0]
    assert row['quote'] == '议题一已表决：赞成4票、反对1票、弃权0票。'
    assert '议题二未提供表决记录' in row['context']
    assert row['actual_status'] == '以本项来源原文明确记载为限；未明确部分待核。'
    assert 'application_date' not in row and 'calculated_expiry' not in row
    assert all(card['applied_to_asset'] is False for card in result['rule_cards'])
    assert result['legal_verified'] is False
    assert '不证明原文支持该分类' in result['notice']


def test_internal_submission_is_not_archived_as_an_application_date(world):
    cases, cid, source, ref = world
    quote = '技术方案P于2026-10-10由员工提交'
    source.write_text(quote + '，仅有内部材料。', encoding='utf-8')
    cases.store.register(source.name); parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    ref.update(quote=quote, sha256=cases.read_material(cid, source.name)['sha256'])
    result = save(cases, cid, 'ip', [{'field': 'filing_date', 'citation': ref}])
    row = result['entries'][0]
    assert row['field'] == 'source_excerpt'
    assert result['classification_audit'][0]['requested_field'] == 'filing_date'
    assert row['label'] == '来源原文'
    body = cases.read_note(cid, result['id'], limit=16000)['content']
    assert quote in body and '｜申请日期' not in body


@pytest.mark.parametrize('document_type', ['minutes', 'proposal'])
def test_corporate_document_is_real_editable_docx_not_the_internal_register(world, document_type):
    from docx import Document
    from pathlib import Path
    from hashlib import sha256
    cases, cid, source, ref = world
    entries = [{'field': 'votes', 'citation': ref}]
    result = save(cases, cid, 'corporate', entries, document_type=document_type, filename='公司文稿.docx')
    path = Path(result['path'])
    assert path.is_file() and path.suffix == '.docx'
    assert result['sha256'] == sha256(path.read_bytes()).hexdigest()
    actual = '\n'.join(p.text for p in Document(path).paragraphs)
    assert actual == result['body_text']
    assert ref['quote'] in actual
    assert '完整片段上下文' not in actual and ref['sha256'] not in actual
    assert '未提供授权公告' not in actual  # Unrelated full context remains internal.
    assert '未提供授权公告' in cases.read_note(cid, result['id'], limit=16000)['content']
    assert '相关结果本稿待核' in actual
    if document_type == 'proposal':
        assert '拟提请股东会审议材料所述担保事项' in actual
    assert result['user_summary'] and result['ready_to_submit'] is False
    again = save(cases, cid, 'corporate', entries, document_type=document_type, filename=path.name)
    assert again['path'] != result['path'] and path.exists()


@pytest.mark.parametrize('domain,document_type,filename', [
    ('ip', 'minutes', '记录.docx'), ('corporate', 'unknown', '记录.docx'),
    ('corporate', '', '记录.docx'), ('corporate', 'minutes', '../记录.docx')])
def test_invalid_document_options_save_nothing(world, domain, document_type, filename):
    cases, cid, source, ref = world
    field = 'status' if domain == 'ip' else 'votes'
    with pytest.raises(ValueError):
        save(cases, cid, domain, [{'field': field, 'citation': ref}],
             document_type=document_type, filename=filename)
    assert cases.get(cid)['total_notes'] == 0


def test_source_change_during_docx_publish_rolls_back_note_and_new_file(world, monkeypatch):
    import source_bound_registers as module
    cases, cid, source, ref = world
    original = module._publish
    def publish_then_change(*args):
        result = original(*args)
        source.write_text('变更后的材料', encoding='utf-8')
        return result
    monkeypatch.setattr(module, '_publish', publish_then_change)
    with pytest.raises(ValueError):
        save(cases, cid, 'corporate', [{'field': 'votes', 'citation': ref}],
             document_type='minutes', filename='记录.docx')
    assert cases.get(cid)['total_notes'] == 0
    assert not list((cases.root / 'drafts').glob('*.docx'))


@pytest.mark.parametrize('field', ['certificate_term', 'internal_estimate', 'date_context'])
def test_date_canonicalization_retains_known_terms_and_event_words(world, field):
    cases, cid, source, ref = world
    ref['quote'] = '境内商标证载期至2028-06-30；内部表预计2030到期，未给依据。'
    result = save(cases, cid, 'ip', [{'field': field, 'citation': ref}])
    assert result['entries'][0]['field'] == 'source_excerpt'
    assert result['classification_audit'][0]['requested_field'] == field
    assert result['entries'][0]['quote'] == ref['quote']
    assert ref['quote'] in cases.read_note(cid, result['id'], limit=16000)['content']


def test_conflicting_corporate_correction_does_not_publish_file(world):
    cases, cid, source, ref = world
    entries = [{'field': 'votes', 'citation': ref}]
    first = save(cases, cid, 'corporate', entries)
    save(cases, cid, 'corporate', entries, supersedes=first['id'])
    result = save(cases, cid, 'corporate', entries, supersedes=first['id'],
                  document_type='minutes', filename='冲突.docx')
    assert result['saved'] is False and 'path' not in result
    assert result['body_text'] == '' and '本次未保存' in result['user_summary']
    assert not (cases.root / 'drafts' / '冲突.docx').exists()


def test_source_already_changed_prevents_corporate_document(world):
    cases, cid, source, ref = world
    source.write_text('替换材料', encoding='utf-8')
    with pytest.raises(ValueError):
        save(cases, cid, 'corporate', [{'field': 'votes', 'citation': ref}],
             document_type='minutes', filename='过期.docx')
    assert cases.get(cid)['total_notes'] == 0
    assert not (cases.root / 'drafts' / '过期.docx').exists()


def exported_note_text(cases, cid, identifier, monkeypatch):
    import business_server as api
    from docx import Document
    monkeypatch.setattr(api, 'cases', cases)
    monkeypatch.setattr(api.material_server, 'store', cases.store)
    result = api.export_case(cid, '回归台账.docx', note_ids=[identifier])
    return '\n'.join(p.text for p in Document(result['path']).paragraphs)


@pytest.mark.parametrize('domain,field,quote,wrong_label', [
    ('ip', 'intended_use', '拟用商标山海智研尚未申请', '拟使用地'),
    ('ip', 'application_place', '国内商标B证书', '拟申请地'),
    ('compliance', 'acceptance', '未提供受理回执', '验收情况'),
])
def test_v5_actual_misclassification_replay_is_neutral_in_note_and_export(
        world, monkeypatch, domain, field, quote, wrong_label):
    cases, cid, source, ref = world
    source.write_text(quote, encoding='utf-8')
    cases.store.register(source.name); parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    ref.update(quote=quote, sha256=cases.read_material(cid, source.name)['sha256'])
    result = save(cases, cid, domain, [{'field': field, 'citation': ref}])
    row = result['entries'][0]
    assert row['field'] == 'source_excerpt'
    assert row['label'] == '来源原文'
    assert row['classification_verified'] is False
    assert result['classification_audit'][0]['requested_field'] == field
    assert 'requested_field' not in row
    note = cases.read_note(cid, result['id'], limit=16000)['content']
    word = exported_note_text(cases, cid, result['id'], monkeypatch)
    for content in [note, word]:
        assert quote in content
        assert '事项1｜' + wrong_label not in content
        assert '模型候选分类（未核验；不是事实字段）：' + field in content


def tracking_world(world, material, pairs):
    cases, cid, source, ref = world
    source.write_text(material, encoding='utf-8')
    cases.store.register(source.name); parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    ref['sha256'] = cases.read_material(cid, source.name)['sha256']
    entries = [{'field': field, 'citation': {**ref, 'quote': quote}} for field, quote in pairs]
    return cases, cid, source, entries


def test_compliance_tracking_is_computed_and_archived_with_known_sent(world, monkeypatch):
    text = ('参考日2026-11-05。意见截止2026-11-10。11月3日内部决定反馈；'
            '台账明确11月4日已通过通知邮箱发送，未提供受理回执。')
    pairs = [('evidence_status', '参考日2026-11-05'), ('feedback_deadline', '意见截止2026-11-10'),
             ('decision', '11月3日内部决定反馈'), ('submission', '台账明确11月4日已通过通知邮箱发送'),
             ('acceptance', '未提供受理回执')]
    cases, cid, source, entries = tracking_world(world, text, pairs)
    tracking = {'as_of': '2026-11-05', 'as_of_entry': 0,
                'deadlines': [{'entry': 1, 'date': '2026-11-10', 'year_basis': 'explicit'}]}
    result = save(cases, cid, 'compliance', entries, tracking=tracking)
    assert result['tracking']['deadlines'][0]['days_from_reference'] == 5
    assert result['tracking']['deadlines'][0]['date_semantics_verified'] is False
    word = exported_note_text(cases, cid, result['id'], monkeypatch)
    note = cases.read_note(cid, result['id'], limit=16000)['content']
    for body in [note, word, result['tracking_text']]:
        assert '参考日：2026-11-05' in body
        assert '相差5个自然日' in body
        assert '11月3日内部决定反馈' in body and '11月4日已通过通知邮箱发送' in body
        assert '先核投递记录和回执，不安排重复首次提交' in body
        assert '未提供受理回执' in body
        assert '报告尚未提交' not in body


def test_two_dates_with_missing_year_are_explicit_conditional_calendar_comparisons(world, monkeypatch):
    text = '参考日2026-11-05。材料A：11月20日前交整改报告。材料B：意见截止11月10日。无决策、提交或回执记录。'
    pairs = [('evidence_status', '参考日2026-11-05'), ('report_deadline', '11月20日前交整改报告'),
             ('feedback_deadline', '意见截止11月10日'), ('evidence_status', '无决策、提交或回执记录')]
    cases, cid, source, entries = tracking_world(world, text, pairs)
    tracking = {'as_of': '2026-11-05', 'as_of_entry': 0, 'deadlines': [
        {'entry': 1, 'date': '2026-11-20', 'year_basis': 'same_as_reference_assumption'},
        {'entry': 2, 'date': '2026-11-10', 'year_basis': 'same_as_reference_assumption'}]}
    result = save(cases, cid, 'compliance', entries, tracking=tracking)
    assert [d['days_from_reference'] for d in result['tracking']['deadlines']] == [15, 5]
    word = exported_note_text(cases, cid, result['id'], monkeypatch)
    assert '年份未给，暂按参考日同年假设' in word
    assert '11月20日前交整改报告' in word and '意见截止11月10日' in word
    assert '不认定实际未决定、未提交或未受理' in word


@pytest.mark.parametrize('mutation', ['invented_date', 'other_reference', 'bad_index',
                                     'fake_sent', 'fake_year', 'invalid_date'])
def test_tracking_rejects_unsupported_values_without_saving(world, mutation):
    text = '参考日2026-11-05。意见截止11月10日。'
    cases, cid, source, entries = tracking_world(world, text, [
        ('evidence_status', '参考日2026-11-05'), ('feedback_deadline', '意见截止11月10日')])
    tracking = {'as_of': '2026-11-05', 'as_of_entry': 0, 'deadlines': [
        {'entry': 1, 'date': '2026-11-10', 'year_basis': 'same_as_reference_assumption'}]}
    if mutation == 'invented_date': tracking['deadlines'][0]['date'] = '2026-11-20'
    if mutation == 'other_reference': tracking['as_of'] = '2026-11-06'
    if mutation == 'bad_index': tracking['deadlines'][0]['entry'] = 9
    if mutation == 'fake_sent': tracking['sent'] = True
    if mutation == 'fake_year': tracking['deadlines'][0]['year_basis'] = 'explicit'
    if mutation == 'invalid_date': tracking['deadlines'][0]['date'] = '2026-02-30'
    with pytest.raises(ValueError):
        save(cases, cid, 'compliance', entries, tracking=tracking)
    assert cases.get(cid)['total_notes'] == 0


@pytest.mark.parametrize('reference,chosen,days,relation', [
    ('2024-02-28', '2024-03-01', 2, 'before_date'),
    ('2026-11-10', '2026-11-10', 0, 'same_date'),
    ('2026-11-11', '2026-11-10', -1, 'after_date'),
])
def test_calendar_boundaries_do_not_create_execution_or_receipt_states(world, reference, chosen, days, relation):
    text = f'参考日{reference}。意见截止{chosen}。材料无提交记录。'
    cases, cid, source, entries = tracking_world(world, text, [
        ('evidence_status', f'参考日{reference}'), ('feedback_deadline', f'意见截止{chosen}'),
        ('submission', '材料无提交记录')])
    result = save(cases, cid, 'compliance', entries, tracking={
        'as_of': reference, 'as_of_entry': 0,
        'deadlines': [{'entry': 1, 'date': chosen, 'year_basis': 'explicit'}]})
    item = result['tracking']['deadlines'][0]
    assert item['days_from_reference'] == days and item['date_relation'] == relation
    assert not any(k in item for k in ['submitted', 'accepted', 'overdue', 'legal_deadline'])
    assert '材料无提交记录' in result['tracking_text']
    assert '报告尚未提交' not in result['tracking_text']


def test_explicit_different_year_cannot_be_laundered_to_same_year_assumption(world):
    text = '参考日2026-11-05。意见截止2025年11月10日。'
    cases, cid, source, entries = tracking_world(world, text, [
        ('evidence_status', '参考日2026-11-05'), ('feedback_deadline', '意见截止2025年11月10日')])
    with pytest.raises(ValueError):
        save(cases, cid, 'compliance', entries, tracking={'as_of': '2026-11-05', 'as_of_entry': 0,
            'deadlines': [{'entry': 1, 'date': '2026-11-10', 'year_basis': 'same_as_reference_assumption'}]})
    assert cases.get(cid)['total_notes'] == 0


@pytest.mark.parametrize('quote,basis', [
    ('意见截止2026-011-10', 'explicit'),
    ('意见截止2026年11月010日', 'explicit'),
    ('意见截止011月10日', 'same_as_reference_assumption'),
    ('意见截止11月010日', 'same_as_reference_assumption'),
    ('意见截止2025年 11月10日', 'same_as_reference_assumption'),
    ('意见截止2025 年\t11月10日', 'same_as_reference_assumption'),
])
def test_malformed_dates_and_spaced_explicit_years_are_not_certified(world, quote, basis):
    text = '参考日2026-11-05。' + quote
    cases, cid, source, entries = tracking_world(world, text, [
        ('evidence_status', '参考日2026-11-05'), ('feedback_deadline', quote)])
    with pytest.raises(ValueError):
        save(cases, cid, 'compliance', entries, tracking={'as_of': '2026-11-05', 'as_of_entry': 0,
            'deadlines': [{'entry': 1, 'date': '2026-11-10', 'year_basis': basis}]})
    assert cases.get(cid)['total_notes'] == 0


def test_minutes_consolidate_repeated_sources_and_keep_every_quote_at_readable_size(world):
    from docx import Document
    text = ('全部虚构，供隔离实测。有限责任公司共有3名董事且三人实际到会。'
            '录音对议题一“更换仓库门锁”清楚记录三票赞成；议题二“扩建仓库”'
            '只录到张说现在不做、王说先看成本，赵没有发言。会议记录签字页未提供。')
    pairs = [('entity', '有限责任公司共有3名董事且三人实际到会'),
             ('participants', '有限责任公司共有3名董事且三人实际到会'),
             ('agenda', '议题一“更换仓库门锁”'),
             ('votes', '录音对议题一“更换仓库门锁”清楚记录三票赞成'),
             ('agenda', '议题二“扩建仓库”'),
             ('votes', '议题二“扩建仓库”只录到张说现在不做、王说先看成本，赵没有发言'),
             ('signature', '会议记录签字页未提供')]
    cases, cid, source, entries = tracking_world(world, text, pairs)
    result = save(cases, cid, 'corporate', entries, document_type='minutes', filename='纪要.docx')
    doc = Document(result['path'])
    body = '\n'.join(p.text for p in doc.paragraphs)
    assert all(quote in body for _, quote in pairs)
    assert body.count(source.name) == 1
    assert '相关结果本稿待核' in body and '本稿不新增执行授权、负责人、期限或生效条件' in body
    assert doc.styles['Normal'].font.size.pt >= 11
    assert doc.styles['Heading 1'].font.size.pt >= 11
    assert body == result['body_text']
