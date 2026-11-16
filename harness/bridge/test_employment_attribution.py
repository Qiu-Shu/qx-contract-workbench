"""Attribution is part of the sourced proposition, not a free analysis label."""
import pytest

from employment_review import save_employment_review
from test_employment_decisions import source_case


def save_opinion(tmp_path, source, text, field='risk'):
    cases,cid,ref=source_case(tmp_path,source)
    item=dict(topic='人员与材料核对',fact='见原文',source='合成材料',basis='适用条件待核',
              risk='条件待核',action='核对协议与岗位材料',pending='补充岗位及协议原件',citations=[ref])
    item[field]=text
    return save_employment_review(cases,cid,'dispute',[item])


@pytest.mark.parametrize('claim',[
    '目前仅能确认员工自述离职前接触技术秘密',
    '员工表示离职前接触技术秘密',
    '员工承认离职前接触技术秘密',
    '据员工陈述，其离职前接触技术秘密',
    '根据公司说明，员工离职前接触技术秘密',
    '公司称员工离职前接触技术秘密',
    '员工表示应进一步核查涉密情况',
    '员工自述的确接触过技术秘密',
])
def test_analysis_cannot_add_a_speaker_to_an_unattributed_statement(tmp_path,claim):
    source='员工离职前接触技术秘密，已履行竞业6个月。'
    independent='不能据此认定协议整体有效或无效，也不能单凭该陈述确定其当然属于适格主体。'
    result=save_opinion(tmp_path,source,claim+'，'+independent)
    assert claim not in result['content']
    assert source in result['content']
    assert independent in result['content']
    assert '核对协议与岗位材料' in result['content']
    assert result['review_changes']


@pytest.mark.parametrize('field',['basis','action','pending','topic'])
def test_attribution_does_not_bypass_binding_by_changing_fields(tmp_path,field):
    claim='公司称员工已收到通知'
    result=save_opinion(tmp_path,'员工已收到通知。',claim+'；核对送达记录。',field)
    assert claim not in result['content']
    assert '核对送达记录' in result['content']


@pytest.mark.parametrize('source,claim',[
    ('员工称公司已发出通知。','公司称已发出通知'),
    ('员工自述已返岗；公司仍未提供通知原件。','员工自述已收到通知'),
    ('公司否认员工自述已收到通知。','员工自述已收到通知'),
    ('尚不能确认员工表示已经同意解除。','员工表示已经同意解除'),
])
def test_a_different_proposition_or_qualifier_cannot_lend_attribution(tmp_path,source,claim):
    result=save_opinion(tmp_path,source,claim+'。请补充通知原件。')
    assert '风险：'+claim not in result['content']
    assert source in result['content']
    assert '请补充通知原件' in result['content']


@pytest.mark.parametrize('text',[
    '若员工自述已经收到通知，仍应核对送达及内容。',
    '不能仅凭员工自述认定通知已经送达。',
    '请核实员工是否表示同意解除，并保留不同意见。',
    '建议向员工询问通知情况，并要求公司说明发送过程。',
    '员工自述的证明力应结合其他证据判断。',
    '劳动者可以主张约定补偿；具体金额仍需核对。',
])
def test_legal_conditions_and_requests_are_not_attributed_facts(tmp_path,text):
    result=save_opinion(tmp_path,'员工是否收到通知未说明。',text)
    assert text in result['content']


def test_an_exact_sourced_speaker_is_kept(tmp_path):
    source='员工自述离职前接触技术秘密。'
    result=save_opinion(tmp_path,source,source+'其真实性仍需结合其他证据核对。')
    assert '风险：'+source in result['content']
    assert '其真实性仍需结合其他证据核对' in result['content']


def test_missing_source_is_not_presented_as_a_bound_reference(tmp_path):
    cases,cid,_=source_case(tmp_path,'本次未提供通知原件。')
    result=save_employment_review(cases,cid,'dispute',[dict(fact='见原文',source='待核',basis='待核',
        risk='员工自述已收到通知。请补通知原件。',action='核对通知')])
    assert '风险：员工自述已收到通知' not in result['content']
    assert '尚无已匹配原文支持' in result['content']
    assert '请补通知原件' in result['content']


def test_normalization_is_stable_and_does_not_rewrite_independent_analysis(tmp_path):
    original='员工离职前接触技术秘密。'
    first=save_opinion(tmp_path,original,'员工自述离职前接触技术秘密，不能据此认定协议效力。')
    risk=next(line.removeprefix('风险：') for line in first['content'].splitlines() if line.startswith('风险：'))
    from draft_review import DraftReview
    from employment_source_claims import bind_source_attribution
    cases,cid,_=source_case(tmp_path/'second',original)
    review=DraftReview(cases,cid)
    second=bind_source_attribution(dict(risk=risk),[original],review,1)
    assert second['risk']==risk
    assert not review.changes


@pytest.mark.parametrize('field,text',[
    ('action','候选条款不写入“双方确认此前从未约定试用期／未适用试用期”等表述；取得既往劳动合同、入职登记及协商记录后，再判断可否约定试用期。'),
    ('topic','双方陈述并列与冲突（事实基础）'),
    ('basis','双方陈述应并列记载，不得择一记录为既定事实。'),
    ('risk','若在双方陈述冲突且无原始考勤条目、无审批记录的情况下，仅依公司陈述认定旷工并据此处理，事实基础不足，后续易被推翻。'),
    ('pending','员工邮件原文、主管陈述、请假审批记录、三天具体日期均待确认。'),
    ('action','由承办人向公司人事及直接主管确认：是否存在口头、会议、通知等方式的解除或停职安排，时间、参与人、具体内容及员工反应；如有，补充书面记录、通知与送达凭证。确认前保持劳动关系状态为待核。'),
    ('action','由员工明确表态后再定主张；对外文字只询事实与款项，不代员工确认或让步。'),
    ('risk','员工自述不足以单独证明通知已经送达，应核对送达凭证。'),
    ('risk','员工自述的内容仍需核实，应收集通知原件。'),
])
def test_captured_independent_analysis_and_request_frames_survive(tmp_path,field,text):
    result=save_opinion(tmp_path,'员工已收到通知。其他情况未说明。',text,field)
    assert text in result['content']


@pytest.mark.parametrize('payload',[
    '员工已收到通知，且同意解除并结清工资',
    '员工未收到通知，亦未同意解除',
])
def test_reported_payload_cannot_become_an_unattributed_fact(tmp_path,payload):
    result=save_opinion(tmp_path,'员工已收到通知。其他情况未说明。','据员工陈述，'+payload+'。请核对材料。')
    risk=next(line for line in result['content'].splitlines() if line.startswith('风险：'))
    assert all(part not in risk for part in payload.split('，'))
    assert '请核对材料' in risk


def test_a_second_attribution_cannot_borrow_the_first_negation(tmp_path):
    result=save_opinion(tmp_path,'员工已收到通知。其他情况未说明。',
        '不能据员工自述认定通知送达但公司确认员工已经同意解除。')
    assert '不能据员工自述认定通知送达' in result['content']
    assert '公司确认员工已经同意解除' not in result['content']


@pytest.mark.parametrize('claim',[
    '员工自述的内容是已经同意解除',
    '公司说明的情况是员工已经同意解除',
])
def test_a_nominal_wrapper_cannot_hide_a_reported_fact(tmp_path,claim):
    result=save_opinion(tmp_path,'员工已收到通知。其他情况未说明。',claim+'。请补材料。')
    assert claim not in result['content']
    assert '请补材料' in result['content']


@pytest.mark.parametrize('analysis',[
    '这不足以单独证明合法送达',
    '单凭该说法不足以确定送达生效',
])
def test_a_demonstrative_does_not_turn_legal_analysis_into_reported_payload(tmp_path,analysis):
    result=save_opinion(tmp_path,'员工已收到通知。其他情况未说明。',
        '员工称已收到通知，'+analysis+'，应核对送达凭证。')
    assert '员工称已收到通知' not in result['content']
    assert analysis in result['content']
