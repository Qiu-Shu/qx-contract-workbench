"""Current unqualified representation changes must not revive an older identity."""
import pytest

from tests.unit.test_contract_named_stance import named_stance, COMPANY


@pytest.mark.parametrize('question,witness', [
    (f'仍代表乙方{COMPANY}。我代表乙方启越测试设备有限公司。', f'我代表乙方{COMPANY}（供应方）。'),
    (f'我代表乙方{COMPANY}（供应方）。我代表乙方启越测试设备有限公司。', None),
    (f'我代表乙方{COMPANY}（供应方）。我 不再代表供应方。', None),
    (f'我代表乙方{COMPANY}（供应方）。我们已经不再代表供应方。', None),
    (f'我“不会”代表乙方{COMPANY}（供应方）。', None),
])
def test_conflicting_or_revoked_current_declaration_is_not_accepted(question, witness):
    method, manifest, value = named_stance(question, witness=witness)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('prefix', ['现在', '目前', '本次', '暂时'])
@pytest.mark.parametrize('kind', ['company', 'role'])
def test_time_prefixed_current_change_cannot_be_ignored(prefix, kind):
    if kind == 'company':
        question = f'仍代表乙方{COMPANY}。{prefix}我代表乙方启越测试设备有限公司。'
        witness = f'我代表乙方{COMPANY}（供应方）。'
    else:
        question, witness = f'我方是供应方。{prefix}我方是采购方。', None
    method, manifest, value = named_stance(question, witness=witness)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


def test_unparsed_own_declaration_cannot_be_silently_ignored():
    method, manifest, value = named_stance('我方是供应方。我已经作为采购方参加本次审查。')
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('opening,closing', [("'", "'"), ('『', '』')])
def test_multiline_quoted_other_speaker_cannot_establish_user_stance(opening, closing):
    question = f'对方说：{opening}\n我代表乙方{COMPANY}（供应方）。\n{closing}'
    method, manifest, value = named_stance(question)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('statement', ['立场待定。', '我方立场尚未确定。'])
def test_current_uncertainty_cannot_leave_an_earlier_role_active(statement):
    method, manifest, value = named_stance('我方是供应方。' + statement)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('change', [
    '当前不代表供应方。',
    '当前我代表乙方启越测试设备有限公司。',
    '我公司现代表乙方启越测试设备有限公司（采购方）。',
    '我们站在采购方立场。',
    '收到更新后我方已经转为采购方。',
    '请先保持中立。',
    '本人现代表乙方启越测试设备有限公司（采购方）。',
    "单价见 buyer's 报价，我方不再代表供应方。",
    '对方说：“请收件。我方不再代表供应方。',
    '我方今后不再代表供应方。',
    '我方已于上月改为采购方。',
    '我方从下个月起是采购方。',
])
def test_unrecognized_self_role_change_stops_named_continuation(change):
    method, manifest, value = named_stance(f'仍代表乙方{COMPANY}。' + change,
        witness=f'我代表乙方{COMPANY}（供应方）。')
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('comment', [
    '我方不同意以采购方名义签署。',
    '我方不认可供应方的验收方式。',
    '我方不接受采购方的付款安排。',
    '供应方不代表我方利益。',
    '我方认为采购方的付款期限过长。',
    '我方建议供应方作为资料接收方时记录收件日期。',
    '我方与供应方是同一集团。',
    '我方已委托代理律师处理后续事宜。',
    '我方不认可代理人的意见。',
    '我方已核对乙方代表签字页。',
    '我方接受中立第三方评估。',
])
def test_contract_opinion_does_not_revoke_an_explicit_stance(comment):
    method, manifest, value = named_stance('我方是供应方。' + comment)
    assert method.candidate(value, manifest).contract_review.stance == 'supplier'


def test_v3_render_displays_current_and_historical_stance_quotes():
    current = f'仍代表乙方{COMPANY}。'
    prior = f'我代表乙方{COMPANY}（供应方）。'
    method, manifest, value = named_stance(current, witness=prior)
    result = method.candidate(value, manifest)
    assert '本次立场原话：' + current in result.text
    assert '历史立场原话：' + prior in result.text
