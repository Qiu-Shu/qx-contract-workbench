import pytest

from cn_contract.assistant import business


@pytest.mark.parametrize('question', [
    '帮我分析一下这个刑事案件，看看有没有不起诉的可能。',
    '请分析供述矛盾。', '请梳理刑事证据链。', '请提出辩护策略。', '请做刑事证据分析。',
    '请做刑事分析。\n“当前阶段：审查起诉”', '请做刑事分析。\n如果当前阶段：审查起诉',
    '请做刑事证据分析，不需要辩护策略。', '不要辩护策略，请做刑事证据分析。',
])
def test_criminal_requests_use_existing_case_entrance(question):
    assert business.classify(question) == 'case'


@pytest.mark.parametrize('question', [
    '暂时不分析刑事案件，只接收材料。', '不要辩护策略。',
    '客户说“请提出辩护策略”。', '如果进入审查起诉再分析刑事案件。',
    '不要再分析供述矛盾。',
])
def test_criminal_words_cannot_override_latest_hold_or_quote(question):
    assert business.classify(question) is None
