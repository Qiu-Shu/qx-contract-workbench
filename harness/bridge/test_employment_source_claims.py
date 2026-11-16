"""Saved employment facts retain source wording, scope and statement medium."""
import pytest
from employment_review import save_employment_review
from test_employment_decisions import source_case


@pytest.mark.parametrize('field,claim', [
    ('fact','公司考勤记录显示上述期间存在未出勤记录。'),
    ('fact','本轮为员工口头陈述。'),
    ('source','员工口述'),
    ('risk','考勤显示员工未出勤，存在严重违纪。'),
    ('risk','材料中考勤记录显示张三连续旷工。'),
    ('risk','材料中记载的情况属于员工口头陈述。'),
    ('risk','考勤内容待核但考勤记录显示张三连续旷工。'),
])
def test_missing_attendance_content_and_unspecified_medium_cannot_become_facts(tmp_path, field, claim):
    original='公司提供考勤摘录，员工称已申请产检假。具体考勤条目本次未展示，请假审批记录未提供。陈述媒介未说明。'
    cases,cid,ref=source_case(tmp_path,original)
    item=dict(topic='请假与考勤',fact='员工称已申请产检假。',source='合成材料',basis='适用待核',
              risk='事实待核',action='核对具体考勤和审批记录',citations=[ref])
    item[field]=claim
    result=save_employment_review(cases,cid,'termination',[item])
    body=cases.read_note(cid,result['id'])['content']
    assert claim not in body
    assert original in body
    assert result['source_observations'][0]['status']=='source_statement'
    assert result['source_observations'][0]['contexts']==[original]
    assert any(row['original']==claim or claim.startswith(row['original'].rstrip('，')) for row in result['review_changes'])


def test_explicit_positive_source_keeps_its_speaker_and_annual_unit(tmp_path):
    original='HR书面说明：张三年薪120000元。公司考勤记录显示张三11月2日未出勤。员工否认该记录。'
    cases,cid,ref=source_case(tmp_path,original)
    result=save_employment_review(cases,cid,'change',[dict(topic='报酬及考勤',fact='张三月薪120000元，未出勤。',
        source='员工口头陈述',basis='待核',risk='双方陈述冲突',action='核对原件和异议',citations=[ref])])
    body=cases.read_note(cid,result['id'])['content']
    assert original in body
    assert '张三月薪120000元' not in body
    assert '员工口头陈述' not in body


def test_missing_citation_does_not_promote_a_monthly_wage_claim(tmp_path):
    cases,cid,_=source_case(tmp_path,'工资周期未给。')
    result=save_employment_review(cases,cid,'dispute',[dict(topic='覆盖说明',fact='试用期月工资3500元。',
        source='模型概述',basis='待核',risk='待核',action='补充材料')])
    assert '试用期月工资3500元' not in result['content']
    assert result['source_observations'][0]['status']=='unbound'
