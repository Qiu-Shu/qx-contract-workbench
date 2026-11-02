import pytest

from cn_contract.assistant import business


@pytest.mark.parametrize('question', [
    '请做商标侵权初筛。', '请做商标分析。', '帮我整理商标侵权因素。',
    '请做知识产权初筛。', '请分析专利侵权。',
    '请做商标侵权初筛，不需要专利侵权初筛。',
    '不要专利侵权初筛，请做商标侵权初筛。',
])
def test_ip_analysis_uses_existing_case_entrance(question):
    assert business.classify(question) == 'case'


@pytest.mark.parametrize('question', [
    '暂时不做商标侵权初筛，只接收材料。', '不再做商标初筛。',
    '客户说“请做商标侵权初筛”。', '如果收齐材料再做商标分析。',
    '不做商标初筛。', '不进行商标侵权分析。',
])
def test_ip_analysis_respects_hold_and_source_statements(question):
    assert business.classify(question) is None


@pytest.mark.parametrize('question,workflow', [
    ('不做刑事分析。','case'), ('不进行刑事证据分析。','case'),
    ('不做合同审查。','contract'), ('不进行模拟法庭。','court'),
])
def test_new_denial_requests_are_blocked_at_current_business_entry(question, workflow):
    assert business.classify(question) is None
    assert business.rejected(question, workflow)


def test_new_ip_negations_do_not_reinterpret_saved_criminal_snapshots(monkeypatch):
    from cn_contract.assistant.criminal_analysis import select_method, validate_snapshot
    from tests.helpers.criminal_analysis import manifest_for
    manifest = manifest_for('不做刑事分析。')
    # Before D, this phrasing selected C; preserve its immutable record interpretation.
    with monkeypatch.context() as previous:
        previous.setattr(business, '_is_negated', lambda content, match: False)
        snapshot = select_method('case', manifest.question, manifest.sources)
    assert snapshot is not None
    saved = manifest.model_copy(update={'criminal_analysis':snapshot})
    validate_snapshot(saved)
    assert select_method('case', manifest.question, ()) is not None


def test_old_criminal_hold_resume_is_not_changed_by_new_ip_words(monkeypatch):
    from cn_contract.assistant.criminal_analysis import select_method, validate_snapshot
    from tests.helpers.criminal_analysis import manifest_for
    manifest = manifest_for('不要分析\n请整理案件，但不做商标侵权\n刑事证据分析')
    with monkeypatch.context() as previous:
        previous.setitem(business._WORKFLOW_WORDS, 'case', tuple(
            word for word in business._WORKFLOW_WORDS['case'] if word not in business._IP_WORDS))
        snapshot = select_method('case', manifest.question, manifest.sources)
    assert snapshot is not None
    validate_snapshot(manifest.model_copy(update={'criminal_analysis':snapshot}))
