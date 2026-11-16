"""Real-model prose must not lose independent reasoning during normalization."""
import pytest

from test_employment_attribution import save_opinion


def test_medium_restatement_does_not_remove_independent_evidence_analysis(tmp_path):
    source='员工邮件称公司电话通知解除竞业。通话记录未提供。'
    analysis='单方转述难以证明通知已作出或未作出。'
    text='举证的现实困难在于口头通话内容缺少记录，'+analysis
    saved=save_opinion(tmp_path,source,text,'basis')
    assert analysis in saved['content']
    assert '口头通话内容缺少记录' not in saved['content']
    assert '考勤具体内容' not in saved['content']
    assert source in saved['content']
    assert any(c['original']==text for c in saved['review_changes'])


def test_removing_a_medium_does_not_promote_its_remaining_payload(tmp_path):
    saved=save_opinion(tmp_path,'陈述媒介与解除状态未说明。',
        '员工口头说明，已经同意解除，且款项已经结清；不能据此认定合法解除。')
    risk=next(s for s in saved['content'].splitlines() if s.startswith('风险：'))
    assert '已经同意解除' not in risk and '款项已经结清' not in risk
    assert '不能据此认定合法解除' in risk


@pytest.mark.parametrize('text',[
    '凡涉及期限起止、通知到达、补偿到账的结论均待核。',
    '期限起止、补偿支付状态尚待确认。',
])
def test_a_pending_list_stays_whole_instead_of_becoming_a_sentence_fragment(tmp_path,text):
    saved=save_opinion(tmp_path,'竞业协议与到账记录未提供。',text)
    assert text in saved['content']


def test_a_known_payment_assertion_cannot_borrow_a_pending_list_suffix(tmp_path):
    saved=save_opinion(tmp_path,'竞业协议与到账记录未提供。',
        '补偿已经全部到账，期限起止待核。')
    risk=next(s for s in saved['content'].splitlines() if s.startswith('风险：'))
    assert '补偿已经全部到账' not in risk


def test_an_independent_pending_request_after_a_report_is_preserved(tmp_path):
    saved=save_opinion(tmp_path,'陈述媒介与解除状态未说明。',
        '员工口头说明，已经同意解除，且全部款项结清；尚需核实通知内容。')
    assert '尚需核实通知内容' in saved['content']
    assert '全部款项结清' not in saved['content']


def test_a_payment_assertion_does_not_destroy_the_following_pending_list(tmp_path):
    pending='期限起止、通知到达、补偿到账的结论均待核。'
    saved=save_opinion(tmp_path,'竞业协议与到账记录未提供。',
        '补偿已经全部到账，'+pending)
    risk=next(s for s in saved['content'].splitlines() if s.startswith('风险：'))
    assert '补偿已经全部到账' not in risk
    assert pending in risk


@pytest.mark.parametrize('timing',['自到达时','送达后立即','自通知送达之日'])
def test_arrival_alone_does_not_supply_the_effective_release_time(tmp_path,timing):
    claim='竞业义务'+timing+'终止'
    saved=save_opinion(tmp_path,'公司是否发出竞业解除通知及其内容未说明。',
        '情形一（解除已作出并到达）：'+claim+'。请核对通知原文。','basis')
    assert claim not in saved['content']
    assert '有效解除时间' in saved['content']
    assert '请核对通知原文' in saved['content']
